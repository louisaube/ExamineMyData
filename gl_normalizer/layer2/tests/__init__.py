"""
gl_normalizer/layer2/tests - Implémentations des tests par univers

V1: 18 tests pragmatiques (Pareto 90% valeur)

UNIVERSELS (3):
  U-01  Z-score montant calibré
  U-02  Mois absent (attendu vs observé)
  U-03  Journal inattendu

CRISTALLIN (3):
  C-01  Variation M/M > seuil
  C-02  Mois manquant série 12/12
  C-03  Nouveau sous-compte

NOMINATIF_OPE (2):
  NO-01 Z-score inter-sites
  NO-02 Site historique absent

PROCESSUS (2):
  P-01  Rupture cycle mensuel
  P-02  Variation masse > 15% hors été

VENTILATION (2):
  V-01  Solde résiduel > 1%
  V-02  Non-extourne décembre

CUT_OFF (2):
  CU-01 Non-extourne > 31 janvier
  CU-02 Solde post-extourne ≠ 0

TRESORERIE (2):
  TR-01 Virement non apparié 580↔512
  TR-02 Flux unitaire > P99

INVENTAIRE (1):
  IN-01 Immo sans dotation 681

PONCTUEL (1):
  PO-01 Montant > matérialité groupe
"""
