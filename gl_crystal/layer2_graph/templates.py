"""
GL Crystal - Templates de Contrepartie

Chaque famille de comptes a un pattern de contreparties attendu.
La déviation par rapport au template révèle les écritures atypiques.

Exemples:
- 641 (salaires) → {421, 431, 437, 512}  template "paie"
- 613 (loyers) → {401, 486, 488}         template "charge récurrente"
- 606 (fournitures) → {401, 512}         template "achats"
- 706 (produits) → {411, 419, 487}       template "facturation client"

Une charge de fournitures dont la contrepartie est un 758 (transfert de charges)
ou un 471 (attente) viole le pattern.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from ..normalizer.schema import EnrichedEntry


@dataclass
class ContrepartieTemplate:
    """Template de contrepartie pour une famille de comptes."""
    famille: str
    label: str
    contreparties_attendues: Set[str]
    type_template: str
    cristallinite_attendue: str  # "haute", "moyenne", "variable"
    commentaire: str = ""


# Templates par famille de comptes P&L
CONTREPARTIE_TEMPLATES: Dict[str, ContrepartieTemplate] = {
    # Charges de personnel
    '641': ContrepartieTemplate(
        famille='641',
        label='Rémunérations du personnel',
        contreparties_attendues={'421', '425', '431', '437', '442', '512'},
        type_template='paie',
        cristallinite_attendue='haute',
        commentaire='Circuit de paie standard. Contreparties sociales et bancaires.',
    ),
    '645': ContrepartieTemplate(
        famille='645',
        label='Charges de sécurité sociale et de prévoyance',
        contreparties_attendues={'431', '437', '438', '512'},
        type_template='charges_sociales',
        cristallinite_attendue='haute',
        commentaire='Cotisations patronales. Circuits URSSAF, retraite, prévoyance.',
    ),
    '647': ContrepartieTemplate(
        famille='647',
        label='Autres charges sociales',
        contreparties_attendues={'437', '438', '512'},
        type_template='charges_sociales',
        cristallinite_attendue='moyenne',
        commentaire='Formation, médecine du travail, etc.',
    ),

    # Achats et services
    '601': ContrepartieTemplate(
        famille='601',
        label='Achats matières premières',
        contreparties_attendues={'401', '408', '512'},
        type_template='achats',
        cristallinite_attendue='moyenne',
        commentaire='Achats stockés. Fournisseurs habituels.',
    ),
    '602': ContrepartieTemplate(
        famille='602',
        label='Achats autres approvisionnements',
        contreparties_attendues={'401', '408', '512'},
        type_template='achats',
        cristallinite_attendue='moyenne',
        commentaire='Approvisionnements non stockés.',
    ),
    '604': ContrepartieTemplate(
        famille='604',
        label='Achats études et prestations',
        contreparties_attendues={'401', '408', '512'},
        type_template='achats',
        cristallinite_attendue='moyenne',
        commentaire='Sous-traitance, prestations intellectuelles.',
    ),
    '606': ContrepartieTemplate(
        famille='606',
        label='Achats non stockés',
        contreparties_attendues={'401', '512'},
        type_template='achats',
        cristallinite_attendue='moyenne',
        commentaire='Fournitures courantes. Diversité fournisseurs normale.',
    ),
    '607': ContrepartieTemplate(
        famille='607',
        label='Achats de marchandises',
        contreparties_attendues={'401', '408', '512'},
        type_template='achats',
        cristallinite_attendue='moyenne',
        commentaire='Négoce. Stock intermédiaire.',
    ),

    # Services extérieurs
    '611': ContrepartieTemplate(
        famille='611',
        label='Sous-traitance générale',
        contreparties_attendues={'401', '408', '488'},
        type_template='services',
        cristallinite_attendue='moyenne',
        commentaire='Peut passer par ABT pour lissage.',
    ),
    '613': ContrepartieTemplate(
        famille='613',
        label='Locations',
        contreparties_attendues={'401', '486', '488'},
        type_template='charge_recurrente',
        cristallinite_attendue='haute',
        commentaire='Loyer mensuel fixe. Peut passer par ABT (488) ou CCA (486).',
    ),
    '614': ContrepartieTemplate(
        famille='614',
        label='Charges locatives',
        contreparties_attendues={'401', '488'},
        type_template='charge_recurrente',
        cristallinite_attendue='haute',
        commentaire='Charges de copropriété, régularisations.',
    ),
    '615': ContrepartieTemplate(
        famille='615',
        label='Entretien et réparations',
        contreparties_attendues={'401', '408', '512'},
        type_template='services',
        cristallinite_attendue='moyenne',
        commentaire='Maintenance courante. Peut être diverse.',
    ),
    '616': ContrepartieTemplate(
        famille='616',
        label='Primes d\'assurance',
        contreparties_attendues={'401', '486', '488'},
        type_template='charge_recurrente',
        cristallinite_attendue='haute',
        commentaire='Annuelles ou mensualisées. CCA/ABT fréquent.',
    ),
    '617': ContrepartieTemplate(
        famille='617',
        label='Études et recherches',
        contreparties_attendues={'401', '408'},
        type_template='services',
        cristallinite_attendue='moyenne',
        commentaire='Prestations intellectuelles.',
    ),
    '618': ContrepartieTemplate(
        famille='618',
        label='Divers',
        contreparties_attendues={'401', '512'},
        type_template='services',
        cristallinite_attendue='variable',
        commentaire='Catégorie fourre-tout. Vigilance.',
    ),

    # Autres services extérieurs
    '622': ContrepartieTemplate(
        famille='622',
        label='Rémunérations intermédiaires et honoraires',
        contreparties_attendues={'401', '421', '431', '512'},
        type_template='honoraires',
        cristallinite_attendue='moyenne',
        commentaire='Experts, avocats, consultants. Peut inclure personnel externe.',
    ),
    '623': ContrepartieTemplate(
        famille='623',
        label='Publicité, publications, relations publiques',
        contreparties_attendues={'401', '512'},
        type_template='services',
        cristallinite_attendue='variable',
        commentaire='Marketing, communication.',
    ),
    '625': ContrepartieTemplate(
        famille='625',
        label='Déplacements, missions et réceptions',
        contreparties_attendues={'401', '421', '512'},
        type_template='frais',
        cristallinite_attendue='variable',
        commentaire='Notes de frais. Peut passer par le personnel.',
    ),
    '626': ContrepartieTemplate(
        famille='626',
        label='Frais postaux et de télécommunications',
        contreparties_attendues={'401', '512'},
        type_template='services',
        cristallinite_attendue='haute',
        commentaire='Abonnements télécom. Réguliers.',
    ),
    '627': ContrepartieTemplate(
        famille='627',
        label='Services bancaires',
        contreparties_attendues={'512'},
        type_template='frais_bancaires',
        cristallinite_attendue='haute',
        commentaire='Frais bancaires. Contrepartie 512 quasi-exclusive.',
    ),

    # Impôts et taxes
    '631': ContrepartieTemplate(
        famille='631',
        label='Impôts, taxes sur rémunérations',
        contreparties_attendues={'442', '447', '512'},
        type_template='taxes',
        cristallinite_attendue='haute',
        commentaire='Taxe sur salaires, formation, etc.',
    ),
    '633': ContrepartieTemplate(
        famille='633',
        label='Impôts, taxes et versements assimilés',
        contreparties_attendues={'447', '488', '512'},
        type_template='taxes',
        cristallinite_attendue='moyenne',
        commentaire='CFE, CVAE. Souvent via ABT.',
    ),
    '635': ContrepartieTemplate(
        famille='635',
        label='Autres impôts et taxes',
        contreparties_attendues={'447', '488', '512'},
        type_template='taxes',
        cristallinite_attendue='moyenne',
        commentaire='Taxes diverses.',
    ),

    # Charges financières
    '661': ContrepartieTemplate(
        famille='661',
        label='Charges d\'intérêts',
        contreparties_attendues={'164', '512', '518'},
        type_template='financier',
        cristallinite_attendue='haute',
        commentaire='Intérêts sur emprunts.',
    ),
    '666': ContrepartieTemplate(
        famille='666',
        label='Pertes de change',
        contreparties_attendues={'512'},
        type_template='financier',
        cristallinite_attendue='variable',
        commentaire='Écarts de conversion.',
    ),

    # Dotations
    '681': ContrepartieTemplate(
        famille='681',
        label='Dotations aux amortissements et provisions',
        contreparties_attendues={'28', '29', '39', '49', '15'},
        type_template='dotation',
        cristallinite_attendue='haute',
        commentaire='Écritures automatiques. Très régulières.',
    ),
    '686': ContrepartieTemplate(
        famille='686',
        label='Dotations aux provisions financières',
        contreparties_attendues={'29', '49', '15'},
        type_template='dotation',
        cristallinite_attendue='haute',
        commentaire='Provisions financières.',
    ),
    '687': ContrepartieTemplate(
        famille='687',
        label='Dotations aux provisions exceptionnelles',
        contreparties_attendues={'15'},
        type_template='dotation',
        cristallinite_attendue='variable',
        commentaire='Provisions exceptionnelles. Par nature ponctuelles.',
    ),

    # Produits d'exploitation
    '706': ContrepartieTemplate(
        famille='706',
        label='Prestations de services',
        contreparties_attendues={'411', '419', '487'},
        type_template='facturation_client',
        cristallinite_attendue='variable',
        commentaire='Dépend du mode de facturation (unitaire, forfait, subvention).',
    ),
    '707': ContrepartieTemplate(
        famille='707',
        label='Ventes de marchandises',
        contreparties_attendues={'411', '419'},
        type_template='facturation_client',
        cristallinite_attendue='variable',
        commentaire='Ventes au détail ou négoce.',
    ),
    '708': ContrepartieTemplate(
        famille='708',
        label='Produits des activités annexes',
        contreparties_attendues={'411', '512'},
        type_template='facturation_client',
        cristallinite_attendue='variable',
        commentaire='Activités accessoires.',
    ),

    # Reprises
    '781': ContrepartieTemplate(
        famille='781',
        label='Reprises sur amortissements et provisions',
        contreparties_attendues={'28', '29', '39', '49', '15'},
        type_template='reprise',
        cristallinite_attendue='haute',
        commentaire='Contrepartie des dotations.',
    ),
    '786': ContrepartieTemplate(
        famille='786',
        label='Reprises sur provisions financières',
        contreparties_attendues={'29', '49', '15'},
        type_template='reprise',
        cristallinite_attendue='haute',
        commentaire='Reprises financières.',
    ),
    '787': ContrepartieTemplate(
        famille='787',
        label='Reprises sur provisions exceptionnelles',
        contreparties_attendues={'15'},
        type_template='reprise',
        cristallinite_attendue='variable',
        commentaire='Reprises exceptionnelles.',
    ),

    # Transferts de charges
    '791': ContrepartieTemplate(
        famille='791',
        label='Transferts de charges d\'exploitation',
        contreparties_attendues={'6'},  # N'importe quel compte de charge
        type_template='transfert',
        cristallinite_attendue='variable',
        commentaire='Réimputation de charges. Signal à investiguer.',
    ),
}


def check_template_conformity(
    famille: str,
    contrepartie: str
) -> Tuple[bool, str]:
    """
    Vérifie si une contrepartie est conforme au template.

    Args:
        famille: Famille de compte (3 chiffres)
        contrepartie: Compte de contrepartie

    Returns:
        (est_conforme, raison)
    """
    template = CONTREPARTIE_TEMPLATES.get(famille)
    if not template:
        return True, "Pas de template défini"

    # Vérifie si la contrepartie match un des préfixes attendus
    for prefix in template.contreparties_attendues:
        if contrepartie.startswith(prefix):
            return True, f"Conforme au template {template.type_template}"

    return False, f"Contrepartie {contrepartie} atypique pour {famille}"


def get_atypical_arcs(
    entries: List[EnrichedEntry]
) -> List[Dict]:
    """
    Identifie les arcs atypiques (contreparties non conformes au template).

    Args:
        entries: Liste des écritures enrichies

    Returns:
        Liste de dicts décrivant les arcs atypiques
    """
    atypical = []

    for entry in entries:
        if not entry.famille or not entry.contrepartie_comptes:
            continue

        for cp in entry.contrepartie_comptes:
            is_conforme, raison = check_template_conformity(entry.famille, cp)
            if not is_conforme:
                atypical.append({
                    'compte': entry.compte_general,
                    'famille': entry.famille,
                    'contrepartie': cp,
                    'analytique': entry.analytique,
                    'mois': entry.mois_comptable,
                    'montant': abs(entry.montant_signe),
                    'libelle': entry.libelle_ecriture,
                    'raison': raison,
                })

    return atypical


def compute_template_stats(
    entries: List[EnrichedEntry]
) -> Dict[str, Dict]:
    """
    Calcule les statistiques de conformité par famille.

    Returns:
        Dict {famille: {n_total, n_conformes, n_atypiques, taux_conformite}}
    """
    stats = defaultdict(lambda: {
        'n_total': 0,
        'n_conformes': 0,
        'n_atypiques': 0,
        'contreparties_vues': defaultdict(int),
    })

    for entry in entries:
        if not entry.famille:
            continue

        famille = entry.famille
        stats[famille]['n_total'] += 1

        if entry.contrepartie_comptes:
            for cp in entry.contrepartie_comptes:
                stats[famille]['contreparties_vues'][cp] += 1
                is_conforme, _ = check_template_conformity(famille, cp)
                if is_conforme:
                    stats[famille]['n_conformes'] += 1
                else:
                    stats[famille]['n_atypiques'] += 1

    # Calcule les taux
    result = {}
    for famille, data in stats.items():
        total_cp = data['n_conformes'] + data['n_atypiques']
        result[famille] = {
            'n_total': data['n_total'],
            'n_conformes': data['n_conformes'],
            'n_atypiques': data['n_atypiques'],
            'taux_conformite': data['n_conformes'] / total_cp if total_cp > 0 else 1.0,
            'top_contreparties': dict(
                sorted(data['contreparties_vues'].items(),
                       key=lambda x: x[1], reverse=True)[:5]
            ),
        }

    return result


def suggest_template_update(
    entries: List[EnrichedEntry],
    min_occurrences: int = 10,
    min_ratio: float = 0.1
) -> List[Dict]:
    """
    Suggère des mises à jour de templates basées sur les données observées.

    Si une contrepartie non prévue apparaît fréquemment, elle devrait
    peut-être être ajoutée au template.

    Args:
        entries: Écritures
        min_occurrences: Nombre minimum d'occurrences
        min_ratio: Ratio minimum par rapport au total

    Returns:
        Liste de suggestions
    """
    # Compte les contreparties par famille
    cp_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    famille_totals: Dict[str, int] = defaultdict(int)

    for entry in entries:
        if not entry.famille or not entry.contrepartie_comptes:
            continue

        famille_totals[entry.famille] += 1
        for cp in entry.contrepartie_comptes:
            cp_counts[entry.famille][cp] += 1

    suggestions = []
    for famille, cp_dict in cp_counts.items():
        template = CONTREPARTIE_TEMPLATES.get(famille)
        if not template:
            continue

        total = famille_totals[famille]
        for cp, count in cp_dict.items():
            # Est-ce déjà dans le template ?
            if any(cp.startswith(p) for p in template.contreparties_attendues):
                continue

            # Est-ce assez fréquent pour suggérer ?
            ratio = count / total if total > 0 else 0
            if count >= min_occurrences and ratio >= min_ratio:
                suggestions.append({
                    'famille': famille,
                    'contrepartie': cp,
                    'occurrences': count,
                    'ratio': ratio,
                    'suggestion': f"Ajouter {cp} au template {famille}",
                })

    return sorted(suggestions, key=lambda x: x['occurrences'], reverse=True)
