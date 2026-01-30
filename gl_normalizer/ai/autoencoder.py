"""
Autoencoder Anomaly Detection
=============================

Détection d'anomalies basée sur un réseau de neurones Autoencoder.

Principe:
- L'autoencoder apprend à compresser puis reconstruire les données normales
- Les anomalies ont une erreur de reconstruction élevée
- Apprentissage non supervisé (pas besoin d'exemples de fraude)

Architecture:
    Input → Encoder → Latent Space → Decoder → Output

    Anomaly Score = ||Input - Output||² (MSE)

Usage:
    detector = AutoencoderDetector(df)
    detector.fit(epochs=50)
    anomalies = detector.get_anomalies()
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from sklearn.preprocessing import StandardScaler, LabelEncoder

# Vérifier si PyTorch est disponible
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


@dataclass
class AutoencoderResult:
    """Résultat pour une écriture"""
    index: int
    reconstruction_error: float
    is_anomaly: bool
    percentile: float


@dataclass
class AutoencoderAnalysis:
    """Analyse complète Autoencoder"""
    total_entries: int
    nb_anomalies: int
    anomaly_rate: float
    threshold: float
    threshold_percentile: float
    training_loss: float
    validation_loss: float
    error_distribution: Dict[str, float]


# Définir la classe Autoencoder seulement si PyTorch est disponible
if TORCH_AVAILABLE:
    class Autoencoder(nn.Module):
        """Réseau Autoencoder PyTorch"""

        def __init__(
            self,
            input_dim: int,
            encoding_dim: int = 8,
            hidden_dims: List[int] = None,
        ):
            super().__init__()

            if hidden_dims is None:
                hidden_dims = [32, 16]

            # Encoder
            encoder_layers = []
            prev_dim = input_dim
            for dim in hidden_dims:
                encoder_layers.extend([
                    nn.Linear(prev_dim, dim),
                    nn.BatchNorm1d(dim),
                    nn.ReLU(),
                    nn.Dropout(0.2),
                ])
                prev_dim = dim
            encoder_layers.append(nn.Linear(prev_dim, encoding_dim))
            self.encoder = nn.Sequential(*encoder_layers)

            # Decoder (miroir de l'encoder)
            decoder_layers = []
            prev_dim = encoding_dim
            for dim in reversed(hidden_dims):
                decoder_layers.extend([
                    nn.Linear(prev_dim, dim),
                    nn.BatchNorm1d(dim),
                    nn.ReLU(),
                    nn.Dropout(0.2),
                ])
                prev_dim = dim
            decoder_layers.append(nn.Linear(prev_dim, input_dim))
            self.decoder = nn.Sequential(*decoder_layers)

        def forward(self, x):
            encoded = self.encoder(x)
            decoded = self.decoder(encoded)
            return decoded

        def encode(self, x):
            return self.encoder(x)
else:
    Autoencoder = None


class AutoencoderDetector:
    """
    Détecteur d'anomalies basé sur Autoencoder.

    Avantages:
    - Capture les relations non-linéaires complexes
    - Très efficace pour les grandes dimensions
    - Peut détecter des patterns subtils
    """

    def __init__(
        self,
        df: pd.DataFrame,
        encoding_dim: int = 8,
        hidden_dims: List[int] = None,
        threshold_percentile: float = 95,
    ):
        """
        Initialise le détecteur Autoencoder.

        Args:
            df: DataFrame avec les écritures comptables
            encoding_dim: Dimension de l'espace latent
            hidden_dims: Dimensions des couches cachées
            threshold_percentile: Percentile pour définir le seuil d'anomalie
        """
        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch est requis pour l'Autoencoder. "
                "Installez-le avec: pip install torch"
            )

        self.df = df.copy()
        self.encoding_dim = encoding_dim
        self.hidden_dims = hidden_dims or [32, 16]
        self.threshold_percentile = threshold_percentile

        self.model = None
        self.scaler = StandardScaler()
        self.label_encoders = {}
        self.features = []
        self.threshold = None
        self.reconstruction_errors = None

    def _engineer_features(self) -> pd.DataFrame:
        """Crée les features pour l'autoencoder"""
        df = self.df.copy()

        # Date features
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df["jour_semaine"] = df["date"].dt.dayofweek
            df["jour_mois"] = df["date"].dt.day
            df["mois"] = df["date"].dt.month
            df["est_fin_mois"] = (df["jour_mois"] >= 25).astype(int)
            df["est_weekend"] = (df["jour_semaine"] >= 5).astype(int)
            df["est_lundi"] = (df["jour_semaine"] == 0).astype(int)
            df["est_vendredi"] = (df["jour_semaine"] == 4).astype(int)
            df["trimestre"] = df["date"].dt.quarter

        # Montant features
        if "montant" in df.columns:
            df["montant_abs"] = df["montant"].abs()
            df["log_montant"] = np.log1p(df["montant_abs"])
            df["signe_montant"] = np.sign(df["montant"])

            # Montants ronds
            for base in [10, 100, 1000, 10000]:
                col = f"mod_{base}"
                df[col] = (df["montant_abs"] % base == 0).astype(int)

            # Premier chiffre (Benford)
            df["premier_chiffre"] = df["montant_abs"].apply(
                lambda x: int(str(int(x))[0]) if x > 0 else 0
            )

        # Compte features
        if "compte" in df.columns:
            df["classe_compte"] = df["compte"].astype(str).str[0]
            df["racine_2"] = df["compte"].astype(str).str[:2]

            # Encoder la classe
            if "classe_compte" not in self.label_encoders:
                self.label_encoders["classe_compte"] = LabelEncoder()
                df["classe_compte_enc"] = self.label_encoders["classe_compte"].fit_transform(
                    df["classe_compte"].fillna("0")
                )
            else:
                df["classe_compte_enc"] = self.label_encoders["classe_compte"].transform(
                    df["classe_compte"].fillna("0")
                )

        # Journal features
        if "journal" in df.columns:
            od_journals = ["OD", "AN", "RAN", "EXT", "EXTOURNE", "SIT", "SITUATION"]
            df["est_journal_od"] = df["journal"].str.upper().isin(od_journals).astype(int)

            # Encoder le journal
            if "journal" not in self.label_encoders:
                self.label_encoders["journal"] = LabelEncoder()
                df["journal_enc"] = self.label_encoders["journal"].fit_transform(
                    df["journal"].fillna("UNKNOWN")
                )
            else:
                # Gérer les valeurs inconnues
                known = set(self.label_encoders["journal"].classes_)
                df["journal_clean"] = df["journal"].fillna("UNKNOWN").apply(
                    lambda x: x if x in known else "UNKNOWN"
                )
                df["journal_enc"] = self.label_encoders["journal"].transform(
                    df["journal_clean"]
                )

        # Agrégations par compte
        if "compte" in df.columns and "montant_abs" in df.columns:
            compte_stats = df.groupby("compte")["montant_abs"].agg(["mean", "std", "count"])
            compte_stats.columns = ["compte_mean", "compte_std", "compte_count"]
            df = df.merge(compte_stats, left_on="compte", right_index=True, how="left")

            df["ecart_moyenne"] = (
                (df["montant_abs"] - df["compte_mean"]) /
                df["compte_std"].replace(0, 1)
            ).fillna(0)

        return df

    def _select_features(self, df: pd.DataFrame) -> List[str]:
        """Sélectionne les features numériques disponibles"""
        numeric_features = [
            "montant_abs", "log_montant", "signe_montant",
            "jour_semaine", "jour_mois", "mois", "trimestre",
            "est_fin_mois", "est_weekend", "est_lundi", "est_vendredi",
            "mod_10", "mod_100", "mod_1000", "mod_10000",
            "premier_chiffre", "classe_compte_enc", "journal_enc",
            "est_journal_od", "ecart_moyenne",
            "compte_mean", "compte_std", "compte_count",
        ]

        available = []
        for feat in numeric_features:
            if feat in df.columns and pd.api.types.is_numeric_dtype(df[feat]):
                if df[feat].notna().mean() > 0.5:
                    available.append(feat)

        return available

    def fit(
        self,
        epochs: int = 50,
        batch_size: int = 256,
        learning_rate: float = 0.001,
        validation_split: float = 0.2,
        verbose: bool = True,
    ) -> "AutoencoderDetector":
        """
        Entraîne l'autoencoder.

        Args:
            epochs: Nombre d'époques d'entraînement
            batch_size: Taille des batchs
            learning_rate: Taux d'apprentissage
            validation_split: Proportion pour validation
            verbose: Afficher la progression

        Returns:
            Self pour chaînage
        """
        # Feature engineering
        df_features = self._engineer_features()
        self.features = self._select_features(df_features)

        if len(self.features) < 3:
            raise ValueError(f"Pas assez de features: {self.features}")

        # Préparer les données
        X = df_features[self.features].fillna(0).values.astype(np.float32)
        X_scaled = self.scaler.fit_transform(X)

        # Split train/val
        n_val = int(len(X_scaled) * validation_split)
        indices = np.random.permutation(len(X_scaled))
        train_idx, val_idx = indices[n_val:], indices[:n_val]

        X_train = torch.FloatTensor(X_scaled[train_idx])
        X_val = torch.FloatTensor(X_scaled[val_idx])

        train_loader = DataLoader(
            TensorDataset(X_train, X_train),
            batch_size=batch_size,
            shuffle=True,
        )
        val_loader = DataLoader(
            TensorDataset(X_val, X_val),
            batch_size=batch_size,
        )

        # Créer le modèle
        input_dim = len(self.features)
        self.model = Autoencoder(
            input_dim=input_dim,
            encoding_dim=self.encoding_dim,
            hidden_dims=self.hidden_dims,
        )

        # Optimizer et loss
        optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        criterion = nn.MSELoss()

        # Entraînement
        self.training_losses = []
        self.validation_losses = []

        for epoch in range(epochs):
            # Training
            self.model.train()
            train_loss = 0
            for batch_x, _ in train_loader:
                optimizer.zero_grad()
                output = self.model(batch_x)
                loss = criterion(output, batch_x)
                loss.backward()
                optimizer.step()
                train_loss += loss.item()

            train_loss /= len(train_loader)
            self.training_losses.append(train_loss)

            # Validation
            self.model.eval()
            val_loss = 0
            with torch.no_grad():
                for batch_x, _ in val_loader:
                    output = self.model(batch_x)
                    loss = criterion(output, batch_x)
                    val_loss += loss.item()

            val_loss /= len(val_loader)
            self.validation_losses.append(val_loss)

            if verbose and (epoch + 1) % 10 == 0:
                print(f"Epoch {epoch+1}/{epochs} - Train: {train_loss:.6f} - Val: {val_loss:.6f}")

        # Calculer les erreurs de reconstruction sur toutes les données
        self.model.eval()
        X_all = torch.FloatTensor(X_scaled)
        with torch.no_grad():
            reconstructed = self.model(X_all)
            self.reconstruction_errors = ((X_all - reconstructed) ** 2).mean(dim=1).numpy()

        # Définir le seuil
        self.threshold = np.percentile(self.reconstruction_errors, self.threshold_percentile)

        return self

    def get_reconstruction_errors(self) -> pd.Series:
        """
        Retourne les erreurs de reconstruction.

        Returns:
            Series avec les erreurs (plus élevé = plus anormal)
        """
        if self.reconstruction_errors is None:
            raise ValueError("Modèle non entraîné. Appelez fit() d'abord.")

        return pd.Series(
            self.reconstruction_errors,
            index=self.df.index,
            name="reconstruction_error",
        )

    def get_anomalies(
        self,
        threshold: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Retourne les écritures détectées comme anomalies.

        Args:
            threshold: Seuil personnalisé (None = utiliser threshold_percentile)

        Returns:
            DataFrame des anomalies avec scores
        """
        if self.reconstruction_errors is None:
            raise ValueError("Modèle non entraîné. Appelez fit() d'abord.")

        thresh = threshold if threshold is not None else self.threshold
        mask = self.reconstruction_errors > thresh

        result = self.df[mask].copy()
        result["reconstruction_error"] = self.reconstruction_errors[mask]
        result["error_percentile"] = pd.Series(self.reconstruction_errors).rank(pct=True)[mask] * 100

        return result.sort_values("reconstruction_error", ascending=False)

    def get_top_anomalies(self, n: int = 100) -> pd.DataFrame:
        """
        Retourne les N écritures les plus anormales.

        Args:
            n: Nombre d'anomalies à retourner

        Returns:
            DataFrame des top anomalies
        """
        if self.reconstruction_errors is None:
            raise ValueError("Modèle non entraîné. Appelez fit() d'abord.")

        result = self.df.copy()
        result["reconstruction_error"] = self.reconstruction_errors
        result["error_percentile"] = pd.Series(self.reconstruction_errors).rank(pct=True) * 100

        return result.nlargest(n, "reconstruction_error")

    def get_latent_representation(self) -> np.ndarray:
        """
        Retourne la représentation latente des écritures.

        Utile pour visualisation (t-SNE, UMAP) ou clustering.

        Returns:
            Array de shape (n_samples, encoding_dim)
        """
        if self.model is None:
            raise ValueError("Modèle non entraîné. Appelez fit() d'abord.")

        df_features = self._engineer_features()
        X = df_features[self.features].fillna(0).values.astype(np.float32)
        X_scaled = self.scaler.transform(X)

        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X_scaled)
            latent = self.model.encode(X_tensor)

        return latent.numpy()

    def analyze(self) -> AutoencoderAnalysis:
        """
        Effectue une analyse complète.

        Returns:
            AutoencoderAnalysis
        """
        if self.reconstruction_errors is None:
            self.fit()

        nb_anomalies = (self.reconstruction_errors > self.threshold).sum()

        return AutoencoderAnalysis(
            total_entries=len(self.df),
            nb_anomalies=nb_anomalies,
            anomaly_rate=nb_anomalies / len(self.df),
            threshold=self.threshold,
            threshold_percentile=self.threshold_percentile,
            training_loss=self.training_losses[-1] if self.training_losses else 0,
            validation_loss=self.validation_losses[-1] if self.validation_losses else 0,
            error_distribution={
                "min": float(self.reconstruction_errors.min()),
                "max": float(self.reconstruction_errors.max()),
                "mean": float(self.reconstruction_errors.mean()),
                "std": float(self.reconstruction_errors.std()),
                "median": float(np.median(self.reconstruction_errors)),
                "p95": float(np.percentile(self.reconstruction_errors, 95)),
                "p99": float(np.percentile(self.reconstruction_errors, 99)),
            },
        )

    def summary(self) -> Dict:
        """Retourne un résumé de l'analyse"""
        analysis = self.analyze()
        return {
            "total_entries": analysis.total_entries,
            "nb_anomalies": analysis.nb_anomalies,
            "anomaly_rate_pct": round(analysis.anomaly_rate * 100, 2),
            "threshold": round(analysis.threshold, 6),
            "features_used": len(self.features),
            "encoding_dim": self.encoding_dim,
            "training_loss": round(analysis.training_loss, 6),
            "validation_loss": round(analysis.validation_loss, 6),
        }


def detect_anomalies_autoencoder(
    df: pd.DataFrame,
    epochs: int = 50,
    threshold_percentile: float = 95,
) -> pd.DataFrame:
    """
    Fonction utilitaire pour détecter rapidement les anomalies.

    Args:
        df: DataFrame avec les écritures
        epochs: Nombre d'époques d'entraînement
        threshold_percentile: Percentile pour le seuil

    Returns:
        DataFrame des anomalies
    """
    detector = AutoencoderDetector(df, threshold_percentile=threshold_percentile)
    detector.fit(epochs=epochs, verbose=False)
    return detector.get_anomalies()
