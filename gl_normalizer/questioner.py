"""
Questioner - Générateur de questions et fiches de levée
=======================================================

Génère automatiquement des questions pertinentes pour chaque anomalie
détectée et structure le processus de levée de non-conformité.

Usage:
    from gl_normalizer import Questioner

    questioner = Questioner(anomalies, provisions)
    questions = questioner.generate_questions()
    fiche = questioner.generate_fiche_levee()
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from enum import Enum


class AnomalyType(Enum):
    """Types d'anomalies détectées"""
    CONCENTRATION = "concentration"          # Concentration sur un mois
    PROVISION_EXCESSIVE = "provision_excessive"
    PROVISION_INSUFFISANTE = "provision_insuffisante"
    VARIATION_INEXPLIQUEE = "variation_inexpliquee"
    MONTANT_ROND = "montant_rond"
    JOURNAL_OD = "journal_od"
    LIBELLE_SUSPECT = "libelle_suspect"
    ZSCORE_ELEVE = "zscore_eleve"
    BENFORD_ANOMALY = "benford_anomaly"
    PATTERN_REGUL = "pattern_regul"


class ResolutionStatus(Enum):
    """Statut de résolution d'une anomalie"""
    A_TRAITER = "À traiter"
    EN_COURS = "En cours"
    JUSTIFIE = "Justifié"
    A_CORRIGER = "À corriger"
    NON_CONFORME = "Non conforme"
    CLOS = "Clos"


@dataclass
class Question:
    """Question générée pour une anomalie"""
    id: str
    anomaly_type: AnomalyType
    compte: str
    libelle_compte: str
    question: str
    contexte: str
    elements_attendus: List[str]
    priorite: int  # 1=haute, 2=moyenne, 3=basse
    montant_concerne: float = 0
    mois_concerne: Optional[int] = None


@dataclass
class PointLevee:
    """Point de levée de non-conformité"""
    id: str
    question: Question
    status: ResolutionStatus = ResolutionStatus.A_TRAITER
    reponse: str = ""
    justificatifs: List[str] = field(default_factory=list)
    date_creation: datetime = field(default_factory=datetime.now)
    date_resolution: Optional[datetime] = None
    responsable: str = ""
    commentaire_auditeur: str = ""


@dataclass
class FicheLevee:
    """Fiche complète de levée de non-conformité"""
    titre: str
    date_generation: datetime
    periode_analysee: str
    nb_anomalies: int
    points: List[PointLevee]
    synthese: Dict[str, int]
    run_rate_brut: float
    run_rate_estime_apres_levee: float


class Questioner:
    """
    Générateur de questions et fiches de levée.

    Analyse les anomalies détectées et génère:
    - Des questions pertinentes et contextualisées
    - Une fiche de levée de non-conformité structurée
    - Un suivi des résolutions
    """

    # Templates de questions par type d'anomalie
    QUESTION_TEMPLATES = {
        AnomalyType.CONCENTRATION: {
            "question": "Pourquoi {pct:.0f}% des charges du compte {compte} sont-elles concentrées sur le mois de {mois} ?",
            "contexte": "Le compte {compte} ({libelle}) présente une concentration anormale: {montant:,.0f}€ sur {mois} vs {moyenne:,.0f}€/mois en moyenne.",
            "elements": [
                "Justification économique de cette concentration",
                "Factures ou pièces justificatives",
                "Confirmation que ce n'est pas une provision annuelle non lissée",
            ],
        },
        AnomalyType.PROVISION_EXCESSIVE: {
            "question": "Quelle est la justification du niveau de provision de {montant:,.0f}€ sur le compte {compte} ?",
            "contexte": "Le compte {compte} ({libelle}) présente une dotation significativement supérieure au run rate: {montant:,.0f}€ vs run rate de {run_rate:,.0f}€.",
            "elements": [
                "Base de calcul de la provision",
                "Risque ou charge sous-jacent",
                "Date de reprise prévue",
                "Historique des mouvements sur ce compte",
            ],
        },
        AnomalyType.PROVISION_INSUFFISANTE: {
            "question": "Le compte {compte} semble sous-provisionné. Y a-t-il un risque non couvert ?",
            "contexte": "Le compte {compte} ({libelle}) montre un niveau de provision inférieur à l'historique: {montant:,.0f}€ vs {attendu:,.0f}€ attendu.",
            "elements": [
                "Confirmation de l'absence de risque additionnel",
                "Explication de la baisse de provisionnement",
                "Éléments justifiant le nouveau niveau",
            ],
        },
        AnomalyType.VARIATION_INEXPLIQUEE: {
            "question": "Comment expliquez-vous la variation de {variation:+,.0f}€ ({pct:+.0f}%) sur le compte {compte} ?",
            "contexte": "Le compte {compte} ({libelle}) varie de {montant_n1:,.0f}€ (N-1) à {montant_n:,.0f}€ (N), soit {variation:+,.0f}€.",
            "elements": [
                "Événement business justifiant cette variation",
                "Changement de méthode comptable",
                "Reclassement depuis/vers un autre compte",
                "Détail des principales écritures",
            ],
        },
        AnomalyType.MONTANT_ROND: {
            "question": "Le montant rond de {montant:,.0f}€ sur le compte {compte} correspond-il à une estimation ou un calcul réel ?",
            "contexte": "Une écriture de {montant:,.0f}€ (montant rond) a été passée sur le compte {compte} ({libelle}) en {mois}.",
            "elements": [
                "Base de calcul du montant",
                "Pièce justificative ou méthode d'estimation",
                "Confirmation qu'il ne s'agit pas d'un ajustement arbitraire",
            ],
        },
        AnomalyType.JOURNAL_OD: {
            "question": "Quelle est la nature de l'écriture OD de {montant:,.0f}€ sur le compte {compte} ?",
            "contexte": "Une écriture sur journal OD de {montant:,.0f}€ a été passée sur {compte} ({libelle}). Libellé: '{libelle_ecriture}'.",
            "elements": [
                "Nature et justification de l'écriture",
                "Validation hiérarchique",
                "Pièce justificative",
                "Impact sur le run rate",
            ],
        },
        AnomalyType.LIBELLE_SUSPECT: {
            "question": "Pouvez-vous clarifier l'écriture '{libelle_ecriture}' de {montant:,.0f}€ sur le compte {compte} ?",
            "contexte": "Le libellé '{libelle_ecriture}' contient des termes nécessitant clarification (erreur, correction, ajustement, etc.).",
            "elements": [
                "Explication de l'opération",
                "Raison de la correction/ajustement",
                "Validation de la régularisation",
            ],
        },
        AnomalyType.ZSCORE_ELEVE: {
            "question": "Le mois de {mois} présente un écart statistique significatif sur le compte {compte}. Quelle en est la raison ?",
            "contexte": "Le compte {compte} ({libelle}) a un z-score de {zscore:+.1f} en {mois}: {montant:,.0f}€ vs moyenne de {moyenne:,.0f}€.",
            "elements": [
                "Événement exceptionnel justifiant cet écart",
                "Détail des principales écritures du mois",
                "Confirmation du caractère non récurrent",
            ],
        },
        AnomalyType.BENFORD_ANOMALY: {
            "question": "La distribution des montants du compte {compte} présente des anomalies. Les montants sont-ils naturels ?",
            "contexte": "L'analyse Benford révèle une sur-représentation de certains chiffres sur le compte {compte}. Cela peut indiquer des montants estimés ou fabriqués.",
            "elements": [
                "Origine des montants (factures réelles vs estimations)",
                "Explication de la distribution observée",
                "Pièces justificatives pour les montants significatifs",
            ],
        },
        AnomalyType.PATTERN_REGUL: {
            "question": "L'écriture de régularisation '{libelle_ecriture}' de {montant:,.0f}€ est-elle justifiée ?",
            "contexte": "Une écriture identifiée comme régularisation ({pattern}) a été passée sur {compte} ({libelle}).",
            "elements": [
                "Nature de la régularisation",
                "Base de calcul",
                "Validation du cut-off",
            ],
        },
    }

    MOIS_NOMS = {
        1: "janvier", 2: "février", 3: "mars", 4: "avril",
        5: "mai", 6: "juin", 7: "juillet", 8: "août",
        9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre"
    }

    def __init__(
        self,
        df: pd.DataFrame,
        anomalies: List[Dict] = None,
        provisions: List[Dict] = None,
        year: int = None,
    ):
        """
        Initialise le questioner.

        Args:
            df: DataFrame du GL
            anomalies: Liste des anomalies détectées
            provisions: Liste des analyses de provisions
            year: Année analysée
        """
        self.df = df
        self.anomalies = anomalies or []
        self.provisions = provisions or []
        self.year = year or datetime.now().year
        self.questions: List[Question] = []
        self.fiche: Optional[FicheLevee] = None

    def _get_mois_nom(self, mois: int) -> str:
        """Retourne le nom du mois"""
        return self.MOIS_NOMS.get(mois, str(mois))

    def _generate_question_id(self, anomaly_type: AnomalyType, compte: str, idx: int) -> str:
        """Génère un ID unique pour une question"""
        return f"{anomaly_type.value[:3].upper()}-{compte[-4:]}-{idx:03d}"

    def _determine_priority(self, anomaly_type: AnomalyType, montant: float) -> int:
        """Détermine la priorité d'une question"""
        # Priorité basée sur le type et le montant
        base_priority = {
            AnomalyType.PROVISION_EXCESSIVE: 1,
            AnomalyType.VARIATION_INEXPLIQUEE: 1,
            AnomalyType.CONCENTRATION: 2,
            AnomalyType.JOURNAL_OD: 2,
            AnomalyType.LIBELLE_SUSPECT: 2,
            AnomalyType.PROVISION_INSUFFISANTE: 2,
            AnomalyType.ZSCORE_ELEVE: 2,
            AnomalyType.MONTANT_ROND: 3,
            AnomalyType.BENFORD_ANOMALY: 3,
            AnomalyType.PATTERN_REGUL: 3,
        }.get(anomaly_type, 3)

        # Ajuster selon le montant
        if abs(montant) > 100000:
            return max(1, base_priority - 1)
        elif abs(montant) < 5000:
            return min(3, base_priority + 1)

        return base_priority

    def generate_questions(self) -> List[Question]:
        """
        Génère les questions pour toutes les anomalies.

        Returns:
            Liste des questions générées
        """
        self.questions = []
        idx = 0

        # Questions pour les anomalies génériques
        for anomaly in self.anomalies:
            idx += 1
            anomaly_type = self._map_anomaly_type(anomaly)
            template = self.QUESTION_TEMPLATES.get(anomaly_type)

            if template:
                # Préparer les variables pour le template
                vars_dict = self._prepare_template_vars(anomaly, anomaly_type)

                question = Question(
                    id=self._generate_question_id(anomaly_type, anomaly.get("compte", "000000"), idx),
                    anomaly_type=anomaly_type,
                    compte=anomaly.get("compte", ""),
                    libelle_compte=anomaly.get("libelle_compte", ""),
                    question=template["question"].format(**vars_dict),
                    contexte=template["contexte"].format(**vars_dict),
                    elements_attendus=template["elements"],
                    priorite=self._determine_priority(anomaly_type, anomaly.get("montant", 0)),
                    montant_concerne=anomaly.get("montant", 0),
                    mois_concerne=anomaly.get("mois"),
                )
                self.questions.append(question)

        # Questions pour les provisions
        for provision in self.provisions:
            idx += 1
            if provision.get("ecart_decembre", 0) > 0:
                anomaly_type = AnomalyType.PROVISION_EXCESSIVE
            else:
                anomaly_type = AnomalyType.PROVISION_INSUFFISANTE

            template = self.QUESTION_TEMPLATES.get(anomaly_type)
            if template:
                vars_dict = {
                    "compte": provision.get("compte", ""),
                    "libelle": provision.get("libelle_compte", ""),
                    "montant": abs(provision.get("decembre_brut", 0)),
                    "run_rate": provision.get("run_rate", 0),
                    "attendu": provision.get("run_rate", 0),
                }

                question = Question(
                    id=self._generate_question_id(anomaly_type, provision.get("compte", "000000"), idx),
                    anomaly_type=anomaly_type,
                    compte=provision.get("compte", ""),
                    libelle_compte=provision.get("libelle_compte", ""),
                    question=template["question"].format(**vars_dict),
                    contexte=template["contexte"].format(**vars_dict),
                    elements_attendus=template["elements"],
                    priorite=self._determine_priority(anomaly_type, provision.get("ecart_decembre", 0)),
                    montant_concerne=provision.get("ecart_decembre", 0),
                    mois_concerne=12,
                )
                self.questions.append(question)

        # Trier par priorité
        self.questions.sort(key=lambda q: (q.priorite, -abs(q.montant_concerne)))

        return self.questions

    def _map_anomaly_type(self, anomaly: Dict) -> AnomalyType:
        """Mappe une anomalie vers son type"""
        nature = anomaly.get("nature", "").lower()
        source = anomaly.get("source", "").lower()

        if "concentration" in nature or "concentration" in source:
            return AnomalyType.CONCENTRATION
        elif "zscore" in source or "z-score" in nature:
            return AnomalyType.ZSCORE_ELEVE
        elif "benford" in source:
            return AnomalyType.BENFORD_ANOMALY
        elif "od" in source or anomaly.get("journal", "").upper() == "OD":
            return AnomalyType.JOURNAL_OD
        elif "libelle" in source or "keyword" in source:
            return AnomalyType.LIBELLE_SUSPECT
        elif "rond" in nature or anomaly.get("is_round", False):
            return AnomalyType.MONTANT_ROND
        elif "regul" in nature or "pattern" in source:
            return AnomalyType.PATTERN_REGUL
        elif anomaly.get("variation", 0) != 0:
            return AnomalyType.VARIATION_INEXPLIQUEE
        else:
            return AnomalyType.CONCENTRATION

    def _prepare_template_vars(self, anomaly: Dict, anomaly_type: AnomalyType) -> Dict:
        """Prépare les variables pour les templates"""
        mois = anomaly.get("mois", 12)
        return {
            "compte": anomaly.get("compte", "000000"),
            "libelle": anomaly.get("libelle_compte", ""),
            "montant": abs(anomaly.get("montant", 0)),
            "mois": self._get_mois_nom(mois),
            "moyenne": anomaly.get("moyenne", 0),
            "run_rate": anomaly.get("run_rate", 0),
            "attendu": anomaly.get("attendu", 0),
            "variation": anomaly.get("variation", 0),
            "pct": anomaly.get("pct", 0),
            "montant_n": anomaly.get("montant_n", 0),
            "montant_n1": anomaly.get("montant_n1", 0),
            "zscore": anomaly.get("z_score", 0),
            "libelle_ecriture": anomaly.get("libelle", "")[:50],
            "pattern": anomaly.get("pattern", ""),
        }

    def generate_fiche_levee(self, titre: str = None) -> FicheLevee:
        """
        Génère une fiche de levée de non-conformité.

        Args:
            titre: Titre de la fiche

        Returns:
            FicheLevee complète
        """
        if not self.questions:
            self.generate_questions()

        # Créer les points de levée
        points = [
            PointLevee(
                id=q.id,
                question=q,
                status=ResolutionStatus.A_TRAITER,
            )
            for q in self.questions
        ]

        # Synthèse par priorité
        synthese = {
            "priorite_1": sum(1 for q in self.questions if q.priorite == 1),
            "priorite_2": sum(1 for q in self.questions if q.priorite == 2),
            "priorite_3": sum(1 for q in self.questions if q.priorite == 3),
            "montant_total_concerne": sum(abs(q.montant_concerne) for q in self.questions),
        }

        self.fiche = FicheLevee(
            titre=titre or f"Levée de non-conformité - Exercice {self.year}",
            date_generation=datetime.now(),
            periode_analysee=f"Exercice {self.year}",
            nb_anomalies=len(self.questions),
            points=points,
            synthese=synthese,
            run_rate_brut=0,  # À calculer depuis le normalizer
            run_rate_estime_apres_levee=0,
        )

        return self.fiche

    def export_fiche_excel(self, filepath: str):
        """
        Exporte la fiche de levée en Excel.

        Args:
            filepath: Chemin du fichier Excel
        """
        if not self.fiche:
            self.generate_fiche_levee()

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            # Onglet Synthèse
            synthese_data = {
                "Élément": ["Date de génération", "Période", "Nb anomalies",
                           "Priorité 1 (haute)", "Priorité 2 (moyenne)", "Priorité 3 (basse)",
                           "Montant total concerné"],
                "Valeur": [
                    self.fiche.date_generation.strftime("%Y-%m-%d %H:%M"),
                    self.fiche.periode_analysee,
                    self.fiche.nb_anomalies,
                    self.fiche.synthese["priorite_1"],
                    self.fiche.synthese["priorite_2"],
                    self.fiche.synthese["priorite_3"],
                    f"{self.fiche.synthese['montant_total_concerne']:,.0f}€",
                ],
            }
            pd.DataFrame(synthese_data).to_excel(writer, sheet_name="Synthèse", index=False)

            # Onglet Points de levée
            points_data = []
            for p in self.fiche.points:
                points_data.append({
                    "ID": p.id,
                    "Priorité": p.question.priorite,
                    "Type": p.question.anomaly_type.value,
                    "Compte": p.question.compte,
                    "Libellé compte": p.question.libelle_compte,
                    "Question": p.question.question,
                    "Contexte": p.question.contexte,
                    "Montant concerné": p.question.montant_concerne,
                    "Mois": self._get_mois_nom(p.question.mois_concerne) if p.question.mois_concerne else "",
                    "Statut": p.status.value,
                    "Réponse": p.reponse,
                    "Commentaire auditeur": p.commentaire_auditeur,
                })
            pd.DataFrame(points_data).to_excel(writer, sheet_name="Points de levée", index=False)

            # Onglet Éléments attendus
            elements_data = []
            for p in self.fiche.points:
                for elem in p.question.elements_attendus:
                    elements_data.append({
                        "ID Point": p.id,
                        "Compte": p.question.compte,
                        "Élément attendu": elem,
                        "Fourni": "",
                        "Commentaire": "",
                    })
            pd.DataFrame(elements_data).to_excel(writer, sheet_name="Éléments attendus", index=False)

    def export_fiche_text(self) -> str:
        """
        Exporte la fiche en format texte.

        Returns:
            Fiche formatée en texte
        """
        if not self.fiche:
            self.generate_fiche_levee()

        lines = [
            "=" * 80,
            f"FICHE DE LEVÉE DE NON-CONFORMITÉ",
            f"{self.fiche.titre}",
            "=" * 80,
            "",
            f"Date de génération: {self.fiche.date_generation.strftime('%Y-%m-%d %H:%M')}",
            f"Période analysée: {self.fiche.periode_analysee}",
            f"Nombre d'anomalies: {self.fiche.nb_anomalies}",
            "",
            "SYNTHÈSE",
            "-" * 40,
            f"  Priorité 1 (haute):   {self.fiche.synthese['priorite_1']}",
            f"  Priorité 2 (moyenne): {self.fiche.synthese['priorite_2']}",
            f"  Priorité 3 (basse):   {self.fiche.synthese['priorite_3']}",
            f"  Montant concerné:     {self.fiche.synthese['montant_total_concerne']:,.0f}€",
            "",
            "=" * 80,
            "POINTS DE LEVÉE",
            "=" * 80,
        ]

        for i, point in enumerate(self.fiche.points, 1):
            q = point.question
            lines.extend([
                "",
                f"[{q.id}] PRIORITÉ {q.priorite} - {q.anomaly_type.value.upper()}",
                "-" * 60,
                f"Compte: {q.compte} - {q.libelle_compte}",
                f"Montant: {q.montant_concerne:+,.0f}€",
                "",
                f"QUESTION:",
                f"  {q.question}",
                "",
                f"CONTEXTE:",
                f"  {q.contexte}",
                "",
                f"ÉLÉMENTS ATTENDUS:",
            ])
            for elem in q.elements_attendus:
                lines.append(f"  □ {elem}")
            lines.extend([
                "",
                f"RÉPONSE: _______________________________________________",
                "",
                f"STATUT: [ ] À traiter  [ ] Justifié  [ ] À corriger  [ ] Non conforme",
                "",
            ])

        lines.extend([
            "=" * 80,
            "FIN DE LA FICHE",
            "=" * 80,
        ])

        return "\n".join(lines)

    def summary(self) -> Dict:
        """Retourne un résumé"""
        if not self.questions:
            self.generate_questions()

        return {
            "nb_questions": len(self.questions),
            "priorite_1": sum(1 for q in self.questions if q.priorite == 1),
            "priorite_2": sum(1 for q in self.questions if q.priorite == 2),
            "priorite_3": sum(1 for q in self.questions if q.priorite == 3),
            "montant_total": sum(abs(q.montant_concerne) for q in self.questions),
            "types": list(set(q.anomaly_type.value for q in self.questions)),
        }


def generate_questions(
    anomalies: List[Dict],
    provisions: List[Dict] = None,
) -> List[Question]:
    """
    Fonction utilitaire pour générer rapidement des questions.

    Args:
        anomalies: Liste des anomalies
        provisions: Liste des provisions

    Returns:
        Liste de questions
    """
    questioner = Questioner(pd.DataFrame(), anomalies, provisions or [])
    return questioner.generate_questions()


def generate_fiche_levee(
    anomalies: List[Dict],
    provisions: List[Dict] = None,
    year: int = None,
) -> FicheLevee:
    """
    Fonction utilitaire pour générer une fiche de levée.

    Args:
        anomalies: Liste des anomalies
        provisions: Liste des provisions
        year: Année analysée

    Returns:
        FicheLevee
    """
    questioner = Questioner(pd.DataFrame(), anomalies, provisions or [], year)
    return questioner.generate_fiche_levee()
