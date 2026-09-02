/**
 * Traductions multilingues ARTCB Frontend
 * Langues: FR, EN, ZH, ES, PT, IT, RU
 */

export type Language = 'fr' | 'en' | 'zh' | 'es' | 'pt' | 'it' | 'ru';

export interface Translations {
  // Navigation
  nav_dashboard: string;
  nav_encode: string;
  nav_agents: string;
  nav_chain: string;
  nav_pol: string;
  nav_memorize: string;
  nav_graph: string;
  nav_wallets: string;
  nav_mining: string;
  nav_system: string;
  nav_logs: string;
  nav_console: string;
  nav_integrations: string;
  nav_network: string;
  nav_governance: string;
  nav_groups: string;
  nav_api_keys: string;
  nav_agent_memory: string;
  nav_register: string;
  
  // Dashboard
  dashboard_title: string;
  dashboard_subtitle: string;
  dashboard_blocks: string;
  dashboard_pol_score: string;
  dashboard_graphs: string;
  
  // Layout
  layout_visibility: string;
  layout_visibility_private: string;
  layout_visibility_public: string;
  layout_visibility_group: string;
  layout_select_group: string;
  layout_no_group: string;
  layout_create_group_first: string;
  layout_select_wallet: string;
  layout_no_wallet: string;
  layout_create_wallet_first: string;
  layout_language: string;
  
  // Encode
  encode_title: string;
  encode_placeholder: string;
  encode_button: string;
  encode_success: string;
  encode_error: string;
  
  // Agents
  agents_title: string;
  agents_run: string;
  agents_explorer: string;
  agents_critic: string;
  agents_status: string;
  
  // Chain
  chain_title: string;
  chain_blocks: string;
  chain_valid: string;
  chain_invalid: string;
  chain_verify: string;
  chain_block_detail: string;
  chain_back: string;
  chain_timestamp: string;
  chain_hash: string;
  chain_signature: string;
  chain_reward: string;
  chain_contributors: string;
  chain_address: string;
  chain_pol_score: string;
  chain_share: string;
  chain_height: string;
  chain_verification: string;
  chain_epoch_reward: string;
  chain_recent_blocks: string;
  chain_detailed_table: string;
  chain_index: string;
  chain_visibility: string;
  chain_graph_id: string;
  
  // PoL
  pol_title: string;
  pol_score: string;
  pol_compression: string;
  pol_validation: string;
  pol_retrieval: string;
  pol_gauge_title: string;
  pol_gauge_accepted: string;
  pol_gauge_below_threshold: string;
  
  // Common
  loading: string;
  error: string;
  success: string;
  cancel: string;
  confirm: string;
  close: string;
  save: string;
  delete: string;
  edit: string;
  view: string;
  common_back: string;
  common_next: string;
  common_search: string;
  common_filter: string;
  common_export: string;
  common_import: string;
  common_refresh: string;
  common_none: string;
  common_all: string;
  common_yes: string;
  common_no: string;
  common_ok: string;
  common_create: string;
  common_blocks: string;
  common_block: string;
  common_wallet: string;
  common_wallets: string;
  common_group: string;
  common_groups: string;
  common_members: string;
  common_pending: string;
  common_active: string;
  common_inactive: string;
  
  // Status
  status_healthy: string;
  status_unhealthy: string;
  status_pending: string;
  status_completed: string;
  status_failed: string;
  
  // Home Page
  home_title: string;
  home_alerts_debug: string;
  home_kpi_pol: string;
  home_kpi_blocks: string;
  home_kpi_wallets: string;
  home_kpi_graphs: string;
  home_kpi_chain: string;
  home_kpi_network: string;
  home_chain_valid: string;
  home_chain_check: string;
  home_checklist_title: string;
  home_checklist_memorize: string;
  home_checklist_explore: string;
  home_checklist_search: string;
  home_checklist_sign: string;
  home_checklist_goto: string;
  home_demo_last: string;
  home_demo_ok: string;
  home_demo_not_found: string;
  home_activity_heatmap: string;
  home_latest_blocks: string;
  home_view_all: string;
  home_reward_note: string;
  home_ir_live: string;
  home_bio_cta: string;
  home_bio_cta_btn: string;

  bio_title: string;
  bio_subtitle: string;
  bio_fingerprint: string;
  bio_face: string;
  bio_both: string;
  bio_name_label: string;
  bio_name_placeholder: string;
  bio_camera_help: string;
  bio_webauthn_prompt: string;
  bio_unsupported: string;
  bio_login: string;
  bio_login_fingerprint: string;
  bio_login_face: string;
  bio_register_tab: string;
  bio_raw_never_stored: string;
  bio_seed_once: string;
  wallets_bio_title: string;
  
  // Memorize Page
  memorize_title: string;
  memorize_session: string;
  memorize_session_id: string;
  memorize_use_llm: string;
  memorize_use_pool: string;
  memorize_encrypt_transport: string;
  memorize_visibility_current: string;
  memorize_select_group: string;
  memorize_source_title: string;
  memorize_placeholder: string;
  memorize_button: string;
  memorize_button_loading: string;
  memorize_graph_title: string;
  memorize_graph_id: string;
  memorize_nodes: string;
  memorize_sign_block: string;
  memorize_sign_loading: string;
  
  // Graph Page
  graph_title: string;
  graph_title_with_id: string;
  graph_no_graph: string;
  graph_selected: string;
  graph_search_placeholder: string;
  graph_search_button: string;
  graph_tts_button: string;
  graph_sign_button: string;
  graph_found: string;
  graph_error: string;
  graph_block_signed: string;
  
  // Wallets Page
  wallets_title: string;
  wallets_create_title: string;
  wallets_create_placeholder: string;
  wallets_create_button: string;
  wallets_balance: string;
  wallets_address: string;
  wallets_founders_title: string;
  wallets_rewards_title: string;
  wallets_rewards_block: string;
  wallets_rewards_amount: string;
  wallets_rewards_timestamp: string;
  wallets_error: string;
  
  // Mining Page
  mining_title: string;
  mining_hero_title: string;
  mining_hero_subtitle: string;
  mining_epoch: string;
  mining_kpi_pol_session: string;
  mining_kpi_blocks_mined: string;
  mining_kpi_rewards_total: string;
  mining_kpi_halving: string;
  mining_kpi_halving_blocks: string;
  mining_last_result_title: string;
  mining_last_result_pol: string;
  mining_last_result_reversible: string;
  mining_last_result_nodes: string;
  mining_last_result_reward: string;
  mining_launch_hint: string;
  mining_real_scripts: string;
  
  // System Page
  system_title: string;
  system_f3_title: string;
  system_cpu: string;
  system_cores: string;
  system_ram: string;
  system_disk: string;
  system_disk_free: string;
  system_network: string;
  system_hostname: string;
  system_gpu_faiss: string;
  system_gpu_none: string;
  system_gpu_faiss_count: string;
  system_optimizations: string;
  system_workers: string;
  system_chunk_pool: string;
  system_faiss: string;
  system_physical_cores: string;
  system_logical_cores: string;
  system_error_metrics: string;
  system_loading_metrics: string;
  
  // Logs Page
  logs_title: string;
  logs_demo_title: string;
  logs_demo_loading: string;
  logs_rtleg_title: string;
  logs_rtleg_error: string;
  
  // Console Page
  console_title: string;
  console_hint: string;
  console_placeholder: string;
  console_execute: string;
  console_unknown_command: string;
  console_type_help: string;
  console_welcome: string;
  
  // Components
  agent_panel_title: string;
  agent_panel_empty: string;
  agent_explorer: string;
  agent_critic: string;
  reconstruct_title: string;
  reconstruct_original: string;
  reconstruct_reconstructed: string;
  reconstruct_ok: string;
  block_row_no_blocks: string;

  // API Keys Page
  api_keys_title: string;
  api_keys_token_warning: string;
  api_keys_new_key: string;
  api_keys_active: string;
  api_keys_cursor_usage: string;

  // Agent Memory Page
  agent_memory_title: string;
  agent_memory_tab_status: string;
  agent_memory_tab_memos: string;
  agent_memory_tab_new: string;
  agent_memory_tab_search: string;
  agent_memory_tab_export: string;
  agent_memory_tab_webhooks: string;
  agent_memory_tab_stream: string;
}

export const translations: Record<Language, Partial<Translations> & Pick<Translations, 'nav_dashboard'>> = {
  fr: {
    // Navigation
    nav_dashboard: 'Tableau de bord',
    nav_encode: 'Encoder',
    nav_agents: 'Agents',
    nav_chain: 'Chaîne',
    nav_pol: 'PoL',
    nav_memorize: 'Mémoriser',
    nav_graph: 'Graphe',
    nav_wallets: 'Wallets',
    nav_mining: 'Minage',
    nav_system: 'Système',
    nav_logs: 'Logs',
    nav_console: 'Console',
    nav_integrations: 'Intégrations',
    nav_network: 'Réseau P2P',
    nav_governance: 'Gouvernance',
    nav_groups: 'Groupes',
    nav_api_keys: 'Clés API',
    nav_agent_memory: 'Mémoire IA',
    nav_register: 'S’inscrire',
    // Dashboard
    dashboard_title: 'Tableau de bord ARTCB',
    dashboard_subtitle: 'Mémoire collective décentralisée',
    dashboard_blocks: 'Blocs',
    dashboard_pol_score: 'Score PoL',
    dashboard_graphs: 'Graphes',
    // Layout
    layout_visibility: 'Réseau',
    layout_visibility_private: 'PRIVÉ',
    layout_visibility_public: 'PUBLIC',
    layout_visibility_group: 'GROUPE',
    layout_select_group: 'Sélectionner un groupe',
    layout_no_group: 'Aucun groupe',
    layout_create_group_first: 'Créez un groupe d\'abord',
    layout_select_wallet: 'Sélectionner un wallet',
    layout_no_wallet: 'Aucun wallet',
    layout_create_wallet_first: 'Créez un wallet d\'abord',
    layout_language: 'Langue',
    // Encode
    encode_title: 'Encoder du texte',
    encode_placeholder: 'Entrez votre texte ici...',
    encode_button: 'Encoder',
    encode_success: 'Texte encodé avec succès',
    encode_error: 'Erreur lors de l\'encodage',
    // Agents
    agents_title: 'Agents IA',
    agents_run: 'Exécuter',
    agents_explorer: 'Explorateur',
    agents_critic: 'Critique',
    agents_status: 'Statut',
    // Chain
    chain_title: 'Blockchain',
    chain_blocks: 'Blocs',
    chain_valid: 'Chaîne valide',
    chain_invalid: 'Chaîne invalide',
    chain_verify: 'Vérifier',
    chain_block_detail: 'Détail du bloc',
    chain_back: '← retour',
    chain_timestamp: 'Horodatage',
    chain_hash: 'Hash',
    chain_signature: 'Signature',
    chain_reward: 'Récompense',
    chain_contributors: 'Contributeurs',
    chain_address: 'Adresse',
    chain_pol_score: 'Score PoL',
    chain_share: 'Part',
    chain_height: 'Hauteur',
    chain_verification: 'Vérification',
    chain_epoch_reward: 'Récompense epoch',
    chain_recent_blocks: 'Blocs récents',
    chain_detailed_table: 'Table détaillée',
    chain_index: 'Index',
    chain_visibility: 'Visibilité',
    chain_graph_id: 'graph_id',
    // PoL
    pol_title: 'Preuve d\'Apprentissage',
    pol_score: 'Score',
    pol_compression: 'Compression',
    pol_validation: 'Validation',
    pol_retrieval: 'Récupération',
    pol_gauge_title: 'Proof-of-Learning',
    pol_gauge_accepted: 'Bloc accepté OK',
    pol_gauge_below_threshold: 'Sous le seuil',
    // Common
    loading: 'Chargement...',
    error: 'Erreur',
    success: 'Succès',
    cancel: 'Annuler',
    confirm: 'Confirmer',
    close: 'Fermer',
    save: 'Enregistrer',
    delete: 'Supprimer',
    edit: 'Modifier',
    view: 'Voir',
    common_back: 'Retour',
    common_next: 'Suivant',
    common_search: 'Rechercher',
    common_filter: 'Filtrer',
    common_export: 'Exporter',
    common_import: 'Importer',
    common_refresh: 'Actualiser',
    common_none: 'Aucun',
    common_all: 'Tous',
    common_yes: 'Oui',
    common_no: 'Non',
    common_ok: 'OK',
    common_create: 'Créer',
    common_blocks: 'Blocs',
    common_block: 'Bloc',
    common_wallet: 'Wallet',
    common_wallets: 'Wallets',
    common_group: 'Groupe',
    common_groups: 'Groupes',
    common_members: 'Membres',
    common_pending: 'En attente',
    common_active: 'Actif',
    common_inactive: 'Inactif',
    // Status
    status_healthy: 'Sain',
    status_unhealthy: 'Défaillant',
    status_pending: 'En attente',
    status_completed: 'Terminé',
    status_failed: 'Échoué',
    // Home Page
    home_title: 'Accueil',
    home_alerts_debug: 'Alertes DEBUG',
    home_kpi_pol: 'PoL',
    home_kpi_blocks: 'Blocs',
    home_kpi_wallets: 'Wallets',
    home_kpi_graphs: 'Graphes',
    home_kpi_chain: 'Chain',
    home_kpi_network: 'réseau',
    home_chain_valid: 'VALID OK',
    home_chain_check: 'CHECK',
    home_checklist_title: 'Parcours rapide',
    home_checklist_memorize: 'Mémoriser un texte',
    home_checklist_explore: 'Explorer le graphe',
    home_checklist_search: 'Rechercher un nœud',
    home_checklist_sign: 'Reconstruire + signer bloc',
    home_checklist_goto: '→ Aller',
    home_demo_last: 'Dernière demo_live :',
    home_demo_ok: 'OK OK',
    home_demo_not_found: 'non trouvée',
    home_activity_heatmap: 'Activité blocs (heatmap)',
    home_latest_blocks: 'Derniers blocs',
    home_view_all: 'Voir tout →',
    home_reward_note: 'Reward genesis epoch : 1 ARTCB / bloc',
    home_ir_live: 'IR live',
    home_bio_cta: 'Bienvenue sur ARTCB — inscrivez-vous par biométrie, par visage, ou les deux.',
    home_bio_cta_btn: 'S’inscrire par biométrie',
    bio_title: 'Inscription biométrique',
    bio_subtitle: 'Empreinte sur le capteur du téléphone, reconnaissance faciale (Face ID / caméra) si vous ne pouvez pas utiliser vos mains, ou les deux.',
    bio_fingerprint: 'Empreinte digitale',
    bio_face: 'Reconnaissance faciale',
    bio_both: 'Empreinte + visage',
    bio_name_label: 'Nom du wallet',
    bio_name_placeholder: 'votre-nom',
    bio_camera_help: 'Caméra avant — reconnaissance faciale',
    bio_webauthn_prompt: 'Confirmez l’empreinte ou Face ID sur l’appareil…',
    bio_unsupported: 'WebAuthn indisponible — la caméra faciale reste proposée. Passez en HTTPS (www.artcb.me).',
    bio_login: 'Connexion biométrie',
    bio_login_fingerprint: 'Se connecter avec l’empreinte',
    bio_login_face: 'Se connecter avec le visage',
    bio_register_tab: 'Créer un compte',
    bio_raw_never_stored: 'Aucune image d’empreinte ou de visage n’est stockée ni écrite dans le livre. Seules des clés publiques WebAuthn (et un secret d’appareil pour la caméra) sont conservées.',
    bio_seed_once: 'Sauvegardez cette seed maintenant — elle ne sera plus affichée.',
    wallets_bio_title: 'Inscription sans mot de passe',
    // Memorize Page
    memorize_title: 'Mémoriser',
    memorize_session: 'Session',
    memorize_session_id: 'session_id',
    memorize_use_llm: 'use_llm',
    memorize_use_pool: 'calcul distribué (pool E2E)',
    memorize_encrypt_transport: 'ML-KEM chiffré (obligatoire)',
    memorize_visibility_current: 'Visibilité actuelle',
    memorize_select_group: 'sélectionnez un groupe dans /groups',
    memorize_source_title: 'Source — grille crafting',
    memorize_placeholder: 'Texte à mémoriser…',
    memorize_button: 'Mémoriser',
    memorize_button_loading: 'Mémorisation…',
    memorize_graph_title: 'Graphe en construction',
    memorize_graph_id: 'graph_id',
    memorize_nodes: 'nœuds',
    memorize_sign_block: 'Signer bloc',
    memorize_sign_loading: 'Signature…',
    // Graph Page
    graph_title: 'Graphe',
    graph_title_with_id: 'Graphe ·',
    graph_no_graph: 'Aucun graphe — allez sur Mémoriser.',
    graph_selected: 'Sélectionné',
    graph_search_placeholder: 'Rechercher…',
    graph_search_button: 'Search',
    graph_tts_button: 'Lire',
    graph_sign_button: 'Signer bloc',
    graph_found: 'Trouvé',
    graph_error: 'Erreur',
    graph_block_signed: 'Bloc signé',
    // Wallets Page
    wallets_title: 'Wallets · coffre',
    wallets_create_title: 'Créer wallet',
    wallets_create_placeholder: 'Nom wallet',
    wallets_create_button: 'Générer',
    wallets_balance: 'Solde',
    wallets_address: 'Adresse',
    wallets_founders_title: 'Founders allocation',
    wallets_rewards_title: 'Rewards',
    wallets_rewards_block: 'Bloc',
    wallets_rewards_amount: 'Reward ₳',
    wallets_rewards_timestamp: 'Date',
    wallets_error: 'Erreur',
    // Mining Page
    mining_title: 'Minage',
    mining_hero_title: 'Proof-of-Learning Mining',
    mining_hero_subtitle: 'Epoch : {reward} ARTCB/bloc — pas de PoW',
    mining_epoch: 'Epoch',
    mining_kpi_pol_session: 'PoL session',
    mining_kpi_blocks_mined: 'Blocs minés',
    mining_kpi_rewards_total: 'Rewards total',
    mining_kpi_halving: 'Halving dans',
    mining_kpi_halving_blocks: 'blocs',
    mining_last_result_title: 'Dernier mining_results (fichier réel)',
    mining_last_result_pol: 'pol',
    mining_last_result_reversible: 'reversible',
    mining_last_result_nodes: 'nodes',
    mining_last_result_reward: 'total_reward_artcb',
    mining_launch_hint: 'Lancer minage via',
    mining_real_scripts: 'scripts réels sur machine utilisateur',
    // System Page
    system_title: 'Système · F3 Debug',
    system_f3_title: '[ F3 ] ARTCB DEBUG SCREEN',
    system_cpu: 'CPU',
    system_cores: 'cœurs',
    system_ram: 'RAM',
    system_disk: 'Disque',
    system_disk_free: 'GB libre',
    system_network: 'Réseau',
    system_hostname: 'Hôte',
    system_gpu_faiss: 'GPU / FAISS',
    system_gpu_none: 'Aucun GPU CUDA détecté',
    system_gpu_faiss_count: 'FAISS GPUs',
    system_optimizations: 'Optimisations',
    system_workers: 'Workers',
    system_chunk_pool: 'Chunk pool',
    system_faiss: 'FAISS',
    system_physical_cores: 'physiques',
    system_logical_cores: 'logiques',
    system_error_metrics: 'Erreur métriques',
    system_loading_metrics: 'Chargement métriques...',
    // Logs Page
    logs_title: 'Logs · chat MC',
    logs_demo_title: 'demo_live_latest.txt',
    logs_demo_loading: 'Chargement…',
    logs_rtleg_title: 'RT-LEG events',
    logs_rtleg_error: 'Erreur',
    // Console Page
    console_title: 'Console CLI',
    console_hint: 'API complète — terminal équivalent',
    console_placeholder: 'help | health | pool status | p2p sync | mining status',
    console_execute: 'Exécuter',
    console_unknown_command: 'Commande inconnue',
    console_type_help: 'Tapez help',
    console_welcome: 'ARTCB Console v0.4 — tapez help',
    // Components
    agent_panel_title: 'Agents duels',
    agent_panel_empty: 'Explorer & Critic commentent pendant l\'encodage…',
    agent_explorer: 'Explorer',
    agent_critic: 'Critic',
    reconstruct_title: 'Reconstruction',
    reconstruct_original: 'Original',
    reconstruct_reconstructed: 'Reconstruit',
    reconstruct_ok: 'OK 100%',
    block_row_no_blocks: 'Aucun bloc',
    api_keys_title: 'Clés API · Accès externe', api_keys_token_warning: 'Copiez ce token maintenant — il ne sera plus affiché', api_keys_new_key: 'Nouvelle clé API', api_keys_active: 'Clés actives', api_keys_cursor_usage: 'Comment utiliser dans Cursor',
    agent_memory_title: 'Agent Memory — ARTCB IA', agent_memory_tab_status: 'Statut', agent_memory_tab_memos: 'Memos', agent_memory_tab_new: 'Nouveau mémo', agent_memory_tab_search: 'Recherche', agent_memory_tab_export: 'Export', agent_memory_tab_webhooks: 'Webhooks', agent_memory_tab_stream: 'Stream',
  },
  
  en: {
    nav_dashboard: 'Dashboard', nav_encode: 'Encode', nav_agents: 'Agents',
    nav_chain: 'Chain', nav_pol: 'PoL', nav_memorize: 'Memorize',
    nav_graph: 'Graph', nav_wallets: 'Wallets', nav_mining: 'Mining',
    nav_system: 'System', nav_logs: 'Logs', nav_console: 'Console',
    nav_integrations: 'Integrations', nav_network: 'P2P Network',
    nav_governance: 'Governance', nav_groups: 'Groups', nav_api_keys: 'API Keys', nav_agent_memory: 'AI Memory', nav_register: 'Sign up',
    dashboard_title: 'ARTCB Dashboard', dashboard_subtitle: 'Decentralized Collective Memory',
    dashboard_blocks: 'Blocks', dashboard_pol_score: 'PoL Score', dashboard_graphs: 'Graphs',
    layout_visibility: 'Network', layout_visibility_private: 'PRIVATE',
    layout_visibility_public: 'PUBLIC', layout_visibility_group: 'GROUP',
    layout_select_group: 'Select a group', layout_no_group: 'No group',
    layout_create_group_first: 'Create a group first', layout_select_wallet: 'Select a wallet',
    layout_no_wallet: 'No wallet', layout_create_wallet_first: 'Create a wallet first',
    layout_language: 'Language',
    encode_title: 'Encode Text', encode_placeholder: 'Enter your text here...',
    encode_button: 'Encode', encode_success: 'Text encoded successfully',
    encode_error: 'Error encoding text',
    agents_title: 'AI Agents', agents_run: 'Run', agents_explorer: 'Explorer',
    agents_critic: 'Critic', agents_status: 'Status',
    chain_title: 'Blockchain', chain_blocks: 'Blocks', chain_valid: 'Chain valid',
    chain_invalid: 'Chain invalid', chain_verify: 'Verify',
    chain_block_detail: 'Block detail', chain_back: '← back',
    chain_timestamp: 'Timestamp', chain_hash: 'Hash', chain_signature: 'Signature',
    chain_reward: 'Reward', chain_contributors: 'Contributors', chain_address: 'Address',
    chain_pol_score: 'PoL Score', chain_share: 'Share', chain_height: 'Height',
    chain_verification: 'Verification', chain_epoch_reward: 'Epoch reward',
    chain_recent_blocks: 'Recent blocks', chain_detailed_table: 'Detailed table',
    chain_index: 'Index', chain_visibility: 'Visibility', chain_graph_id: 'graph_id',
    pol_title: 'Proof of Learning', pol_score: 'Score', pol_compression: 'Compression',
    pol_validation: 'Validation', pol_retrieval: 'Retrieval',
    pol_gauge_title: 'Proof-of-Learning', pol_gauge_accepted: 'Block accepted OK',
    pol_gauge_below_threshold: 'Below threshold',
    loading: 'Loading...', error: 'Error', success: 'Success', cancel: 'Cancel',
    confirm: 'Confirm', close: 'Close', save: 'Save', delete: 'Delete',
    edit: 'Edit', view: 'View',
    common_back: 'Back', common_next: 'Next', common_search: 'Search',
    common_filter: 'Filter', common_export: 'Export', common_import: 'Import',
    common_refresh: 'Refresh', common_none: 'None', common_all: 'All',
    common_yes: 'Yes', common_no: 'No', common_ok: 'OK', common_create: 'Create',
    common_blocks: 'Blocks', common_block: 'Block', common_wallet: 'Wallet',
    common_wallets: 'Wallets', common_group: 'Group', common_groups: 'Groups',
    common_members: 'Members', common_pending: 'Pending', common_active: 'Active',
    common_inactive: 'Inactive',
    status_healthy: 'Healthy', status_unhealthy: 'Unhealthy', status_pending: 'Pending',
    status_completed: 'Completed', status_failed: 'Failed',
    home_title: 'Home', home_alerts_debug: 'DEBUG Alerts',
    home_kpi_pol: 'PoL', home_kpi_blocks: 'Blocks', home_kpi_wallets: 'Wallets',
    home_kpi_graphs: 'Graphs', home_kpi_chain: 'Chain', home_kpi_network: 'network',
    home_chain_valid: 'VALID OK', home_chain_check: 'CHECK',
    home_checklist_title: 'Quick start', home_checklist_memorize: 'Memorize a text',
    home_checklist_explore: 'Explore the graph', home_checklist_search: 'Search a node',
    home_checklist_sign: 'Reconstruct + sign block', home_checklist_goto: '→ Go',
    home_demo_last: 'Last demo_live:', home_demo_ok: 'OK OK',
    home_demo_not_found: 'not found', home_activity_heatmap: 'Block activity (heatmap)',
    home_latest_blocks: 'Latest blocks', home_view_all: 'View all →',
    home_reward_note: 'Genesis epoch reward: 1 ARTCB / block', home_ir_live: 'IR live',
    home_bio_cta: 'Welcome to ARTCB — register with fingerprint, face, or both.',
    home_bio_cta_btn: 'Sign up with biometrics',
    bio_title: 'Biometric registration',
    bio_subtitle: 'Fingerprint on your phone sensor, face unlock if you cannot use your hands, or both.',
    bio_fingerprint: 'Fingerprint',
    bio_face: 'Face recognition',
    bio_both: 'Fingerprint + face',
    bio_name_label: 'Wallet name',
    bio_name_placeholder: 'your-name',
    bio_camera_help: 'Front camera — face recognition',
    bio_webauthn_prompt: 'Confirm fingerprint or Face ID on the device…',
    bio_unsupported: 'WebAuthn unavailable — camera face remains offered. Use HTTPS (www.artcb.me).',
    bio_login: 'Biometric login',
    bio_login_fingerprint: 'Sign in with fingerprint',
    bio_login_face: 'Sign in with face',
    bio_register_tab: 'Create account',
    bio_raw_never_stored: 'No fingerprint or face image is stored or written on-chain. Only WebAuthn public keys (and a device secret for the camera path) are kept.',
    bio_seed_once: 'Save this seed now — it will never be shown again.',
    wallets_bio_title: 'Passwordless registration',
    memorize_title: 'Memorize', memorize_session: 'Session',
    memorize_session_id: 'session_id', memorize_use_llm: 'use_llm',
    memorize_use_pool: 'distributed compute (pool E2E)',
    memorize_encrypt_transport: 'ML-KEM encrypted (required)',
    memorize_visibility_current: 'Current visibility',
    memorize_select_group: 'select a group in /groups',
    memorize_source_title: 'Source — crafting grid',
    memorize_placeholder: 'Text to memorize…', memorize_button: 'Memorize',
    memorize_button_loading: 'Memorizing…', memorize_graph_title: 'Graph building',
    memorize_graph_id: 'graph_id', memorize_nodes: 'nodes',
    memorize_sign_block: 'Sign block', memorize_sign_loading: 'Signing…',
    graph_title: 'Graph', graph_title_with_id: 'Graph ·',
    graph_no_graph: 'No graph — go to Memorize.',
    graph_selected: 'Selected', graph_search_placeholder: 'Search…',
    graph_search_button: 'Search', graph_tts_button: 'Read', graph_sign_button: 'Sign block',
    graph_found: 'Found', graph_error: 'Error', graph_block_signed: 'Block signed',
    wallets_title: 'Wallets · chest', wallets_create_title: 'Create wallet',
    wallets_create_placeholder: 'Wallet name', wallets_create_button: 'Generate',
    wallets_balance: 'Balance', wallets_address: 'Address',
    wallets_founders_title: 'Founders allocation', wallets_rewards_title: 'Rewards',
    wallets_rewards_block: 'Block', wallets_rewards_amount: 'Reward ₳',
    wallets_rewards_timestamp: 'Date', wallets_error: 'Error',
    mining_title: 'Mining', mining_hero_title: 'Proof-of-Learning Mining',
    mining_hero_subtitle: 'Epoch: {reward} ARTCB/block — no PoW',
    mining_epoch: 'Epoch', mining_kpi_pol_session: 'PoL session',
    mining_kpi_blocks_mined: 'Blocks mined', mining_kpi_rewards_total: 'Total rewards',
    mining_kpi_halving: 'Halving in', mining_kpi_halving_blocks: 'blocks',
    mining_last_result_title: 'Last mining_results (real file)',
    mining_last_result_pol: 'pol', mining_last_result_reversible: 'reversible',
    mining_last_result_nodes: 'nodes', mining_last_result_reward: 'total_reward_artcb',
    mining_launch_hint: 'Launch mining via', mining_real_scripts: 'real scripts on user machine',
    system_title: 'System · F3 Debug', system_f3_title: '[ F3 ] ARTCB DEBUG SCREEN',
    system_cpu: 'CPU', system_cores: 'cores', system_ram: 'RAM', system_disk: 'Disk',
    system_disk_free: 'GB free', system_network: 'Network', system_hostname: 'Host',
    system_gpu_faiss: 'GPU / FAISS', system_gpu_none: 'No CUDA GPU detected',
    system_gpu_faiss_count: 'FAISS GPUs', system_optimizations: 'Optimizations',
    system_workers: 'Workers', system_chunk_pool: 'Chunk pool', system_faiss: 'FAISS',
    system_physical_cores: 'physical', system_logical_cores: 'logical',
    system_error_metrics: 'Metrics error', system_loading_metrics: 'Loading metrics...',
    logs_title: 'Logs · MC chat', logs_demo_title: 'demo_live_latest.txt',
    logs_demo_loading: 'Loading…', logs_rtleg_title: 'RT-LEG events',
    logs_rtleg_error: 'Error',
    console_title: 'CLI Console', console_hint: 'Full API — terminal equivalent',
    console_placeholder: 'help | health | pool status | p2p sync | mining status',
    console_execute: 'Execute', console_unknown_command: 'Unknown command',
    console_type_help: 'Type help', console_welcome: 'ARTCB Console v0.4 — type help',
    agent_panel_title: 'Dual agents', agent_panel_empty: 'Explorer & Critic comment during encoding…',
    agent_explorer: 'Explorer', agent_critic: 'Critic',
    reconstruct_title: 'Reconstruction', reconstruct_original: 'Original',
    reconstruct_reconstructed: 'Reconstructed', reconstruct_ok: 'OK 100%',
    block_row_no_blocks: 'No blocks',
    api_keys_title: 'API Keys · External access', api_keys_token_warning: 'Copy this token now — it will not be shown again', api_keys_new_key: 'New API key', api_keys_active: 'Active keys', api_keys_cursor_usage: 'How to use in Cursor',
    agent_memory_title: 'Agent Memory — ARTCB AI', agent_memory_tab_status: 'Status', agent_memory_tab_memos: 'Memos', agent_memory_tab_new: 'New memo', agent_memory_tab_search: 'Search', agent_memory_tab_export: 'Export', agent_memory_tab_webhooks: 'Webhooks', agent_memory_tab_stream: 'Stream',
  },
  
  zh: {
    nav_dashboard: '仪表板', nav_encode: '编码', nav_agents: '代理',
    nav_chain: '区块链', nav_pol: '学习证明', nav_memorize: '记忆',
    nav_graph: '图谱', nav_wallets: '钱包', nav_mining: '挖矿',
    nav_system: '系统', nav_logs: '日志', nav_console: '控制台',
    nav_integrations: '集成', nav_network: 'P2P网络',
    nav_governance: '治理', nav_groups: '群组', nav_api_keys: 'API密钥', nav_agent_memory: 'AI记忆',
    dashboard_title: 'ARTCB 仪表板', dashboard_subtitle: '去中心化集体记忆',
    dashboard_blocks: '区块', dashboard_pol_score: '学习证明分数', dashboard_graphs: '图表',
    layout_visibility: '网络', layout_visibility_private: '私有',
    layout_visibility_public: '公开', layout_visibility_group: '群组',
    layout_select_group: '选择群组', layout_no_group: '无群组',
    layout_create_group_first: '请先创建群组', layout_select_wallet: '选择钱包',
    layout_no_wallet: '无钱包', layout_create_wallet_first: '请先创建钱包',
    layout_language: '语言',
    encode_title: '编码文本', encode_placeholder: '在此输入您的文本...',
    encode_button: '编码', encode_success: '文本编码成功', encode_error: '编码文本时出错',
    agents_title: 'AI代理', agents_run: '运行', agents_explorer: '探索者',
    agents_critic: '评论家', agents_status: '状态',
    chain_title: '区块链', chain_blocks: '区块', chain_valid: '链有效',
    chain_invalid: '链无效', chain_verify: '验证',
    chain_block_detail: '区块详情', chain_back: '← 返回',
    chain_timestamp: '时间戳', chain_hash: '哈希', chain_signature: '签名',
    chain_reward: '奖励', chain_contributors: '贡献者', chain_address: '地址',
    chain_pol_score: '学习证明分数', chain_share: '份额', chain_height: '高度',
    chain_verification: '验证', chain_epoch_reward: '纪元奖励',
    chain_recent_blocks: '最近区块', chain_detailed_table: '详细表格',
    chain_index: '索引', chain_visibility: '可见性', chain_graph_id: '图谱ID',
    pol_title: '学习证明', pol_score: '分数', pol_compression: '压缩',
    pol_validation: '验证', pol_retrieval: '检索',
    pol_gauge_title: '学习证明', pol_gauge_accepted: '区块已接受',
    pol_gauge_below_threshold: '低于阈值',
    loading: '加载中...', error: '错误', success: '成功', cancel: '取消',
    confirm: '确认', close: '关闭', save: '保存', delete: '删除',
    edit: '编辑', view: '查看',
    common_back: '返回', common_next: '下一步', common_search: '搜索',
    common_filter: '筛选', common_export: '导出', common_import: '导入',
    common_refresh: '刷新', common_none: '无', common_all: '全部',
    common_yes: '是', common_no: '否', common_ok: '确定', common_create: '创建',
    common_blocks: '区块', common_block: '区块', common_wallet: '钱包',
    common_wallets: '钱包', common_group: '群组', common_groups: '群组',
    common_members: '成员', common_pending: '待处理', common_active: '活跃',
    common_inactive: '非活跃',
    status_healthy: '健康', status_unhealthy: '不健康', status_pending: '待处理',
    status_completed: '已完成', status_failed: '失败',
    home_title: '首页', home_alerts_debug: 'DEBUG警报',
    home_kpi_pol: '学习证明', home_kpi_blocks: '区块', home_kpi_wallets: '钱包',
    home_kpi_graphs: '图表', home_kpi_chain: '链', home_kpi_network: '网络',
    home_chain_valid: '有效', home_chain_check: '检查',
    home_checklist_title: '快速导航', home_checklist_memorize: '记忆文本',
    home_checklist_explore: '探索图谱', home_checklist_search: '搜索节点',
    home_checklist_sign: '重建+签署区块', home_checklist_goto: '→ 前往',
    home_demo_last: '最后demo_live:', home_demo_ok: 'OK OK',
    home_demo_not_found: '未找到', home_activity_heatmap: '区块活动热图',
    home_latest_blocks: '最新区块', home_view_all: '查看全部 →',
    home_reward_note: '创世纪元奖励：1 ARTCB / 区块', home_ir_live: 'IR实时',
    memorize_title: '记忆', memorize_session: '会话', memorize_session_id: '会话ID',
    memorize_use_llm: '使用LLM', memorize_use_pool: '分布式计算（pool E2E）',
    memorize_encrypt_transport: 'ML-KEM加密（必需）',
    memorize_visibility_current: '当前可见性',
    memorize_select_group: '在/groups中选择群组',
    memorize_source_title: '来源 — 合成网格',
    memorize_placeholder: '要记忆的文本…', memorize_button: '记忆',
    memorize_button_loading: '记忆中…', memorize_graph_title: '构建中的图谱',
    memorize_graph_id: '图谱ID', memorize_nodes: '节点',
    memorize_sign_block: '签署区块', memorize_sign_loading: '签署中…',
    graph_title: '图谱', graph_title_with_id: '图谱·',
    graph_no_graph: '无图谱 — 前往记忆页面。',
    graph_selected: '已选择', graph_search_placeholder: '搜索…',
    graph_search_button: '搜索', graph_tts_button: '朗读', graph_sign_button: '签署区块',
    graph_found: '找到', graph_error: '错误', graph_block_signed: '区块已签署',
    wallets_title: '钱包·宝箱', wallets_create_title: '创建钱包',
    wallets_create_placeholder: '钱包名称', wallets_create_button: '生成',
    wallets_balance: '余额', wallets_address: '地址',
    wallets_founders_title: '创始人分配', wallets_rewards_title: '奖励',
    wallets_rewards_block: '区块', wallets_rewards_amount: '奖励₳',
    wallets_rewards_timestamp: '日期', wallets_error: '错误',
    mining_title: '挖矿', mining_hero_title: '学习证明挖矿',
    mining_hero_subtitle: '纪元：{reward} ARTCB/区块 — 无PoW',
    mining_epoch: '纪元', mining_kpi_pol_session: '学习证明会话',
    mining_kpi_blocks_mined: '已挖区块', mining_kpi_rewards_total: '总奖励',
    mining_kpi_halving: '减半倒计时', mining_kpi_halving_blocks: '区块',
    mining_last_result_title: '最后挖矿结果（真实文件）',
    mining_last_result_pol: 'pol', mining_last_result_reversible: '可逆',
    mining_last_result_nodes: '节点', mining_last_result_reward: '总奖励ARTCB',
    mining_launch_hint: '通过以下启动挖矿', mining_real_scripts: '用户机器上的真实脚本',
    system_title: '系统·F3调试', system_f3_title: '[ F3 ] ARTCB调试屏幕',
    system_cpu: 'CPU', system_cores: '核心', system_ram: '内存', system_disk: '磁盘',
    system_disk_free: 'GB可用', system_network: '网络', system_hostname: '主机名',
    system_gpu_faiss: 'GPU/FAISS', system_gpu_none: '未检测到CUDA GPU',
    system_gpu_faiss_count: 'FAISS GPU数', system_optimizations: '优化',
    system_workers: '工作线程', system_chunk_pool: '块池', system_faiss: 'FAISS',
    system_physical_cores: '物理核心', system_logical_cores: '逻辑核心',
    system_error_metrics: '指标错误', system_loading_metrics: '加载指标中...',
    logs_title: '日志·MC聊天', logs_demo_title: 'demo_live_latest.txt',
    logs_demo_loading: '加载中…', logs_rtleg_title: 'RT-LEG事件',
    logs_rtleg_error: '错误',
    console_title: 'CLI控制台', console_hint: '完整API — 终端等效',
    console_placeholder: 'help | health | pool status | p2p sync | mining status',
    console_execute: '执行', console_unknown_command: '未知命令',
    console_type_help: '输入help', console_welcome: 'ARTCB控制台v0.4 — 输入help',
    agent_panel_title: '双代理', agent_panel_empty: 'Explorer和Critic在编码时评论…',
    agent_explorer: 'Explorer', agent_critic: 'Critic',
    reconstruct_title: '重建', reconstruct_original: '原文',
    reconstruct_reconstructed: '重建', reconstruct_ok: 'OK 100%',
    block_row_no_blocks: '无区块',
    api_keys_title: 'API密钥·外部访问', api_keys_token_warning: '立即复制此令牌——不会再次显示', api_keys_new_key: '新API密钥', api_keys_active: '活跃密钥', api_keys_cursor_usage: '如何在Cursor中使用',
    agent_memory_title: '代理记忆 — ARTCB AI', agent_memory_tab_status: '状态', agent_memory_tab_memos: '备忘', agent_memory_tab_new: '新备忘', agent_memory_tab_search: '搜索', agent_memory_tab_export: '导出', agent_memory_tab_webhooks: 'Webhooks', agent_memory_tab_stream: '流',
  },
  
  es: {
    nav_dashboard: 'Panel', nav_encode: 'Codificar', nav_agents: 'Agentes',
    nav_chain: 'Cadena', nav_pol: 'PoL', nav_memorize: 'Memorizar',
    nav_graph: 'Gráfico', nav_wallets: 'Wallets', nav_mining: 'Minería',
    nav_system: 'Sistema', nav_logs: 'Registros', nav_console: 'Consola',
    nav_integrations: 'Integraciones', nav_network: 'Red P2P',
    nav_governance: 'Gobernanza', nav_groups: 'Grupos', nav_api_keys: 'Claves API', nav_agent_memory: 'Memoria IA',
    dashboard_title: 'Panel ARTCB', dashboard_subtitle: 'Memoria Colectiva Descentralizada',
    dashboard_blocks: 'Bloques', dashboard_pol_score: 'Puntuación PoL', dashboard_graphs: 'Gráficos',
    layout_visibility: 'Red', layout_visibility_private: 'PRIVADO',
    layout_visibility_public: 'PÚBLICO', layout_visibility_group: 'GRUPO',
    layout_select_group: 'Seleccionar grupo', layout_no_group: 'Sin grupo',
    layout_create_group_first: 'Crea un grupo primero', layout_select_wallet: 'Seleccionar wallet',
    layout_no_wallet: 'Sin wallet', layout_create_wallet_first: 'Crea un wallet primero',
    layout_language: 'Idioma',
    encode_title: 'Codificar texto', encode_placeholder: 'Ingrese su texto aquí...',
    encode_button: 'Codificar', encode_success: 'Texto codificado exitosamente',
    encode_error: 'Error al codificar el texto',
    agents_title: 'Agentes IA', agents_run: 'Ejecutar', agents_explorer: 'Explorador',
    agents_critic: 'Crítico', agents_status: 'Estado',
    chain_title: 'Blockchain', chain_blocks: 'Bloques', chain_valid: 'Cadena válida',
    chain_invalid: 'Cadena inválida', chain_verify: 'Verificar',
    chain_block_detail: 'Detalle bloque', chain_back: '← volver',
    chain_timestamp: 'Marca de tiempo', chain_hash: 'Hash', chain_signature: 'Firma',
    chain_reward: 'Recompensa', chain_contributors: 'Contribuidores', chain_address: 'Dirección',
    chain_pol_score: 'Puntuación PoL', chain_share: 'Cuota', chain_height: 'Altura',
    chain_verification: 'Verificación', chain_epoch_reward: 'Recompensa epoch',
    chain_recent_blocks: 'Bloques recientes', chain_detailed_table: 'Tabla detallada',
    chain_index: 'Índice', chain_visibility: 'Visibilidad', chain_graph_id: 'graph_id',
    pol_title: 'Prueba de Aprendizaje', pol_score: 'Puntuación', pol_compression: 'Compresión',
    pol_validation: 'Validación', pol_retrieval: 'Recuperación',
    pol_gauge_title: 'Prueba de Aprendizaje', pol_gauge_accepted: 'Bloque aceptado OK',
    pol_gauge_below_threshold: 'Por debajo del umbral',
    loading: 'Cargando...', error: 'Error', success: 'Éxito', cancel: 'Cancelar',
    confirm: 'Confirmar', close: 'Cerrar', save: 'Guardar', delete: 'Eliminar',
    edit: 'Editar', view: 'Ver',
    common_back: 'Atrás', common_next: 'Siguiente', common_search: 'Buscar',
    common_filter: 'Filtrar', common_export: 'Exportar', common_import: 'Importar',
    common_refresh: 'Actualizar', common_none: 'Ninguno', common_all: 'Todos',
    common_yes: 'Sí', common_no: 'No', common_ok: 'OK', common_create: 'Crear',
    common_blocks: 'Bloques', common_block: 'Bloque', common_wallet: 'Wallet',
    common_wallets: 'Wallets', common_group: 'Grupo', common_groups: 'Grupos',
    common_members: 'Miembros', common_pending: 'Pendiente', common_active: 'Activo',
    common_inactive: 'Inactivo',
    status_healthy: 'Saludable', status_unhealthy: 'No saludable', status_pending: 'Pendiente',
    status_completed: 'Completado', status_failed: 'Fallido',
    home_title: 'Inicio', home_alerts_debug: 'Alertas DEBUG',
    home_kpi_pol: 'PoL', home_kpi_blocks: 'Bloques', home_kpi_wallets: 'Wallets',
    home_kpi_graphs: 'Gráficos', home_kpi_chain: 'Cadena', home_kpi_network: 'red',
    home_chain_valid: 'VÁLIDA OK', home_chain_check: 'VERIFICAR',
    home_checklist_title: 'Inicio rápido', home_checklist_memorize: 'Memorizar texto',
    home_checklist_explore: 'Explorar gráfico', home_checklist_search: 'Buscar nodo',
    home_checklist_sign: 'Reconstruir + firmar bloque', home_checklist_goto: '→ Ir',
    home_demo_last: 'Último demo_live:', home_demo_ok: 'OK OK',
    home_demo_not_found: 'no encontrado', home_activity_heatmap: 'Actividad bloques (mapa calor)',
    home_latest_blocks: 'Últimos bloques', home_view_all: 'Ver todo →',
    home_reward_note: 'Recompensa génesis: 1 ARTCB / bloque', home_ir_live: 'IR en vivo',
    memorize_title: 'Memorizar', memorize_session: 'Sesión', memorize_session_id: 'session_id',
    memorize_use_llm: 'usar LLM', memorize_use_pool: 'cómputo distribuido (pool E2E)',
    memorize_encrypt_transport: 'ML-KEM cifrado (obligatorio)',
    memorize_visibility_current: 'Visibilidad actual',
    memorize_select_group: 'selecciona grupo en /groups',
    memorize_source_title: 'Fuente — cuadrícula de síntesis',
    memorize_placeholder: 'Texto a memorizar…', memorize_button: 'Memorizar',
    memorize_button_loading: 'Memorizando…', memorize_graph_title: 'Gráfico en construcción',
    memorize_graph_id: 'graph_id', memorize_nodes: 'nodos',
    memorize_sign_block: 'Firmar bloque', memorize_sign_loading: 'Firmando…',
    graph_title: 'Gráfico', graph_title_with_id: 'Gráfico ·',
    graph_no_graph: 'Sin gráfico — ve a Memorizar.',
    graph_selected: 'Seleccionado', graph_search_placeholder: 'Buscar…',
    graph_search_button: 'Buscar', graph_tts_button: 'Leer', graph_sign_button: 'Firmar bloque',
    graph_found: 'Encontrado', graph_error: 'Error', graph_block_signed: 'Bloque firmado',
    wallets_title: 'Wallets · cofre', wallets_create_title: 'Crear wallet',
    wallets_create_placeholder: 'Nombre wallet', wallets_create_button: 'Generar',
    wallets_balance: 'Saldo', wallets_address: 'Dirección',
    wallets_founders_title: 'Asignación fundadores', wallets_rewards_title: 'Recompensas',
    wallets_rewards_block: 'Bloque', wallets_rewards_amount: 'Recompensa ₳',
    wallets_rewards_timestamp: 'Fecha', wallets_error: 'Error',
    mining_title: 'Minería', mining_hero_title: 'Minería Prueba-de-Aprendizaje',
    mining_hero_subtitle: 'Época: {reward} ARTCB/bloque — sin PoW',
    mining_epoch: 'Época', mining_kpi_pol_session: 'PoL sesión',
    mining_kpi_blocks_mined: 'Bloques minados', mining_kpi_rewards_total: 'Recompensas total',
    mining_kpi_halving: 'Halving en', mining_kpi_halving_blocks: 'bloques',
    mining_last_result_title: 'Último resultado minería (archivo real)',
    mining_last_result_pol: 'pol', mining_last_result_reversible: 'reversible',
    mining_last_result_nodes: 'nodos', mining_last_result_reward: 'total_reward_artcb',
    mining_launch_hint: 'Iniciar minería via', mining_real_scripts: 'scripts reales en máquina usuario',
    system_title: 'Sistema · F3 Debug', system_f3_title: '[ F3 ] ARTCB PANTALLA DEBUG',
    system_cpu: 'CPU', system_cores: 'núcleos', system_ram: 'RAM', system_disk: 'Disco',
    system_disk_free: 'GB libre', system_network: 'Red', system_hostname: 'Host',
    system_gpu_faiss: 'GPU / FAISS', system_gpu_none: 'Sin GPU CUDA detectada',
    system_gpu_faiss_count: 'FAISS GPUs', system_optimizations: 'Optimizaciones',
    system_workers: 'Workers', system_chunk_pool: 'Chunk pool', system_faiss: 'FAISS',
    system_physical_cores: 'físicos', system_logical_cores: 'lógicos',
    system_error_metrics: 'Error métricas', system_loading_metrics: 'Cargando métricas...',
    logs_title: 'Registros · chat MC', logs_demo_title: 'demo_live_latest.txt',
    logs_demo_loading: 'Cargando…', logs_rtleg_title: 'Eventos RT-LEG',
    logs_rtleg_error: 'Error',
    console_title: 'Consola CLI', console_hint: 'API completa — terminal equivalente',
    console_placeholder: 'help | health | pool status | p2p sync | mining status',
    console_execute: 'Ejecutar', console_unknown_command: 'Comando desconocido',
    console_type_help: 'Escribe help', console_welcome: 'ARTCB Consola v0.4 — escribe help',
    agent_panel_title: 'Agentes duales', agent_panel_empty: 'Explorer y Critic comentan durante la codificación…',
    agent_explorer: 'Explorer', agent_critic: 'Critic',
    reconstruct_title: 'Reconstrucción', reconstruct_original: 'Original',
    reconstruct_reconstructed: 'Reconstruido', reconstruct_ok: 'OK 100%',
    block_row_no_blocks: 'Sin bloques',
    api_keys_title: 'Claves API · Acceso externo', api_keys_token_warning: 'Copia este token ahora — no se mostrará de nuevo', api_keys_new_key: 'Nueva clave API', api_keys_active: 'Claves activas', api_keys_cursor_usage: 'Cómo usar en Cursor',
    agent_memory_title: 'Memoria de Agente — ARTCB IA', agent_memory_tab_status: 'Estado', agent_memory_tab_memos: 'Memos', agent_memory_tab_new: 'Nuevo memo', agent_memory_tab_search: 'Buscar', agent_memory_tab_export: 'Exportar', agent_memory_tab_webhooks: 'Webhooks', agent_memory_tab_stream: 'Stream',
  },
  
  pt: {
    nav_dashboard: 'Painel', nav_encode: 'Codificar', nav_agents: 'Agentes',
    nav_chain: 'Cadeia', nav_pol: 'PoL', nav_memorize: 'Memorizar',
    nav_graph: 'Gráfico', nav_wallets: 'Carteiras', nav_mining: 'Mineração',
    nav_system: 'Sistema', nav_logs: 'Registros', nav_console: 'Console',
    nav_integrations: 'Integrações', nav_network: 'Rede P2P',
    nav_governance: 'Governança', nav_groups: 'Grupos', nav_api_keys: 'Chaves API', nav_agent_memory: 'Memória IA',
    dashboard_title: 'Painel ARTCB', dashboard_subtitle: 'Memória Coletiva Descentralizada',
    dashboard_blocks: 'Blocos', dashboard_pol_score: 'Pontuação PoL', dashboard_graphs: 'Gráficos',
    layout_visibility: 'Rede', layout_visibility_private: 'PRIVADO',
    layout_visibility_public: 'PÚBLICO', layout_visibility_group: 'GRUPO',
    layout_select_group: 'Selecionar grupo', layout_no_group: 'Sem grupo',
    layout_create_group_first: 'Crie um grupo primeiro', layout_select_wallet: 'Selecionar carteira',
    layout_no_wallet: 'Sem carteira', layout_create_wallet_first: 'Crie uma carteira primeiro',
    layout_language: 'Idioma',
    encode_title: 'Codificar texto', encode_placeholder: 'Digite seu texto aqui...',
    encode_button: 'Codificar', encode_success: 'Texto codificado com sucesso',
    encode_error: 'Erro ao codificar texto',
    agents_title: 'Agentes IA', agents_run: 'Executar', agents_explorer: 'Explorador',
    agents_critic: 'Crítico', agents_status: 'Status',
    chain_title: 'Blockchain', chain_blocks: 'Blocos', chain_valid: 'Cadeia válida',
    chain_invalid: 'Cadeia inválida', chain_verify: 'Verificar',
    chain_block_detail: 'Detalhe bloco', chain_back: '← voltar',
    chain_timestamp: 'Carimbo de tempo', chain_hash: 'Hash', chain_signature: 'Assinatura',
    chain_reward: 'Recompensa', chain_contributors: 'Contribuidores', chain_address: 'Endereço',
    chain_pol_score: 'Pontuação PoL', chain_share: 'Quota', chain_height: 'Altura',
    chain_verification: 'Verificação', chain_epoch_reward: 'Recompensa epoch',
    chain_recent_blocks: 'Blocos recentes', chain_detailed_table: 'Tabela detalhada',
    chain_index: 'Índice', chain_visibility: 'Visibilidade', chain_graph_id: 'graph_id',
    pol_title: 'Prova de Aprendizagem', pol_score: 'Pontuação', pol_compression: 'Compressão',
    pol_validation: 'Validação', pol_retrieval: 'Recuperação',
    pol_gauge_title: 'Prova de Aprendizagem', pol_gauge_accepted: 'Bloco aceito OK',
    pol_gauge_below_threshold: 'Abaixo do limiar',
    loading: 'Carregando...', error: 'Erro', success: 'Sucesso', cancel: 'Cancelar',
    confirm: 'Confirmar', close: 'Fechar', save: 'Salvar', delete: 'Excluir',
    edit: 'Editar', view: 'Ver',
    common_back: 'Voltar', common_next: 'Próximo', common_search: 'Pesquisar',
    common_filter: 'Filtrar', common_export: 'Exportar', common_import: 'Importar',
    common_refresh: 'Atualizar', common_none: 'Nenhum', common_all: 'Todos',
    common_yes: 'Sim', common_no: 'Não', common_ok: 'OK', common_create: 'Criar',
    common_blocks: 'Blocos', common_block: 'Bloco', common_wallet: 'Carteira',
    common_wallets: 'Carteiras', common_group: 'Grupo', common_groups: 'Grupos',
    common_members: 'Membros', common_pending: 'Pendente', common_active: 'Ativo',
    common_inactive: 'Inativo',
    status_healthy: 'Saudável', status_unhealthy: 'Não saudável', status_pending: 'Pendente',
    status_completed: 'Concluído', status_failed: 'Falhou',
    home_title: 'Início', home_alerts_debug: 'Alertas DEBUG',
    home_kpi_pol: 'PoL', home_kpi_blocks: 'Blocos', home_kpi_wallets: 'Carteiras',
    home_kpi_graphs: 'Gráficos', home_kpi_chain: 'Cadeia', home_kpi_network: 'rede',
    home_chain_valid: 'VÁLIDA OK', home_chain_check: 'VERIFICAR',
    home_checklist_title: 'Início rápido', home_checklist_memorize: 'Memorizar texto',
    home_checklist_explore: 'Explorar gráfico', home_checklist_search: 'Pesquisar nó',
    home_checklist_sign: 'Reconstruir + assinar bloco', home_checklist_goto: '→ Ir',
    home_demo_last: 'Último demo_live:', home_demo_ok: 'OK OK',
    home_demo_not_found: 'não encontrado', home_activity_heatmap: 'Atividade blocos (mapa calor)',
    home_latest_blocks: 'Últimos blocos', home_view_all: 'Ver tudo →',
    home_reward_note: 'Recompensa gênese: 1 ARTCB / bloco', home_ir_live: 'IR ao vivo',
    memorize_title: 'Memorizar', memorize_session: 'Sessão', memorize_session_id: 'session_id',
    memorize_use_llm: 'usar LLM', memorize_use_pool: 'computação distribuída (pool E2E)',
    memorize_encrypt_transport: 'ML-KEM criptografado (obrigatório)',
    memorize_visibility_current: 'Visibilidade atual',
    memorize_select_group: 'selecione grupo em /groups',
    memorize_source_title: 'Fonte — grade de síntese',
    memorize_placeholder: 'Texto para memorizar…', memorize_button: 'Memorizar',
    memorize_button_loading: 'Memorizando…', memorize_graph_title: 'Gráfico em construção',
    memorize_graph_id: 'graph_id', memorize_nodes: 'nós',
    memorize_sign_block: 'Assinar bloco', memorize_sign_loading: 'Assinando…',
    graph_title: 'Gráfico', graph_title_with_id: 'Gráfico ·',
    graph_no_graph: 'Sem gráfico — vá para Memorizar.',
    graph_selected: 'Selecionado', graph_search_placeholder: 'Pesquisar…',
    graph_search_button: 'Pesquisar', graph_tts_button: 'Ler', graph_sign_button: 'Assinar bloco',
    graph_found: 'Encontrado', graph_error: 'Erro', graph_block_signed: 'Bloco assinado',
    wallets_title: 'Carteiras · cofre', wallets_create_title: 'Criar carteira',
    wallets_create_placeholder: 'Nome carteira', wallets_create_button: 'Gerar',
    wallets_balance: 'Saldo', wallets_address: 'Endereço',
    wallets_founders_title: 'Alocação fundadores', wallets_rewards_title: 'Recompensas',
    wallets_rewards_block: 'Bloco', wallets_rewards_amount: 'Recompensa ₳',
    wallets_rewards_timestamp: 'Data', wallets_error: 'Erro',
    mining_title: 'Mineração', mining_hero_title: 'Mineração Prova-de-Aprendizagem',
    mining_hero_subtitle: 'Época: {reward} ARTCB/bloco — sem PoW',
    mining_epoch: 'Época', mining_kpi_pol_session: 'PoL sessão',
    mining_kpi_blocks_mined: 'Blocos minerados', mining_kpi_rewards_total: 'Total recompensas',
    mining_kpi_halving: 'Halving em', mining_kpi_halving_blocks: 'blocos',
    mining_last_result_title: 'Último resultado mineração (arquivo real)',
    mining_last_result_pol: 'pol', mining_last_result_reversible: 'reversível',
    mining_last_result_nodes: 'nós', mining_last_result_reward: 'total_reward_artcb',
    mining_launch_hint: 'Iniciar mineração via', mining_real_scripts: 'scripts reais na máquina do usuário',
    system_title: 'Sistema · F3 Debug', system_f3_title: '[ F3 ] ARTCB TELA DEBUG',
    system_cpu: 'CPU', system_cores: 'núcleos', system_ram: 'RAM', system_disk: 'Disco',
    system_disk_free: 'GB livre', system_network: 'Rede', system_hostname: 'Host',
    system_gpu_faiss: 'GPU / FAISS', system_gpu_none: 'Sem GPU CUDA detectada',
    system_gpu_faiss_count: 'FAISS GPUs', system_optimizations: 'Otimizações',
    system_workers: 'Workers', system_chunk_pool: 'Chunk pool', system_faiss: 'FAISS',
    system_physical_cores: 'físicos', system_logical_cores: 'lógicos',
    system_error_metrics: 'Erro métricas', system_loading_metrics: 'Carregando métricas...',
    logs_title: 'Registros · chat MC', logs_demo_title: 'demo_live_latest.txt',
    logs_demo_loading: 'Carregando…', logs_rtleg_title: 'Eventos RT-LEG',
    logs_rtleg_error: 'Erro',
    console_title: 'Console CLI', console_hint: 'API completa — terminal equivalente',
    console_placeholder: 'help | health | pool status | p2p sync | mining status',
    console_execute: 'Executar', console_unknown_command: 'Comando desconhecido',
    console_type_help: 'Digite help', console_welcome: 'ARTCB Console v0.4 — digite help',
    agent_panel_title: 'Agentes duais', agent_panel_empty: 'Explorer e Critic comentam durante a codificação…',
    agent_explorer: 'Explorer', agent_critic: 'Critic',
    reconstruct_title: 'Reconstrução', reconstruct_original: 'Original',
    reconstruct_reconstructed: 'Reconstruído', reconstruct_ok: 'OK 100%',
    block_row_no_blocks: 'Sem blocos',
    api_keys_title: 'Chaves API · Acesso externo', api_keys_token_warning: 'Copie este token agora — não será exibido novamente', api_keys_new_key: 'Nova chave API', api_keys_active: 'Chaves ativas', api_keys_cursor_usage: 'Como usar no Cursor',
    agent_memory_title: 'Memória de Agente — ARTCB IA', agent_memory_tab_status: 'Estado', agent_memory_tab_memos: 'Memos', agent_memory_tab_new: 'Novo memo', agent_memory_tab_search: 'Pesquisa', agent_memory_tab_export: 'Exportar', agent_memory_tab_webhooks: 'Webhooks', agent_memory_tab_stream: 'Stream',
  },

  it: {
    nav_dashboard: 'Pannello', nav_encode: 'Codifica', nav_agents: 'Agenti',
    nav_chain: 'Catena', nav_pol: 'PoL', nav_memorize: 'Memorizza',
    nav_graph: 'Grafico', nav_wallets: 'Portafogli', nav_mining: 'Mining',
    nav_system: 'Sistema', nav_logs: 'Log', nav_console: 'Console',
    nav_integrations: 'Integrazioni', nav_network: 'Rete P2P',
    nav_governance: 'Governance', nav_groups: 'Gruppi', nav_api_keys: 'Chiavi API', nav_agent_memory: 'Memoria IA',
    dashboard_title: 'Pannello ARTCB', dashboard_subtitle: 'Memoria Collettiva Decentralizzata',
    dashboard_blocks: 'Blocchi', dashboard_pol_score: 'Punteggio PoL', dashboard_graphs: 'Grafici',
    layout_visibility: 'Rete', layout_visibility_private: 'PRIVATO',
    layout_visibility_public: 'PUBBLICO', layout_visibility_group: 'GRUPPO',
    layout_select_group: 'Seleziona gruppo', layout_no_group: 'Nessun gruppo',
    layout_create_group_first: 'Crea prima un gruppo', layout_select_wallet: 'Seleziona portafoglio',
    layout_no_wallet: 'Nessun portafoglio', layout_create_wallet_first: 'Crea prima un portafoglio',
    layout_language: 'Lingua',
    encode_title: 'Codifica testo', encode_placeholder: 'Inserisci il tuo testo qui...',
    encode_button: 'Codifica', encode_success: 'Testo codificato con successo',
    encode_error: 'Errore nella codifica del testo',
    agents_title: 'Agenti IA', agents_run: 'Esegui', agents_explorer: 'Esploratore',
    agents_critic: 'Critico', agents_status: 'Stato',
    chain_title: 'Blockchain', chain_blocks: 'Blocchi', chain_valid: 'Catena valida',
    chain_invalid: 'Catena non valida', chain_verify: 'Verifica',
    chain_block_detail: 'Dettaglio blocco', chain_back: '← indietro',
    chain_timestamp: 'Data/ora', chain_hash: 'Hash', chain_signature: 'Firma',
    chain_reward: 'Ricompensa', chain_contributors: 'Contributori', chain_address: 'Indirizzo',
    chain_pol_score: 'Punteggio PoL', chain_share: 'Quota', chain_height: 'Altezza',
    chain_verification: 'Verifica', chain_epoch_reward: 'Ricompensa epoch',
    chain_recent_blocks: 'Blocchi recenti', chain_detailed_table: 'Tabella dettagliata',
    chain_index: 'Indice', chain_visibility: 'Visibilità', chain_graph_id: 'graph_id',
    pol_title: 'Prova di Apprendimento', pol_score: 'Punteggio', pol_compression: 'Compressione',
    pol_validation: 'Validazione', pol_retrieval: 'Recupero',
    pol_gauge_title: 'Prova di Apprendimento', pol_gauge_accepted: 'Blocco accettato OK',
    pol_gauge_below_threshold: 'Sotto la soglia',
    loading: 'Caricamento...', error: 'Errore', success: 'Successo', cancel: 'Annulla',
    confirm: 'Conferma', close: 'Chiudi', save: 'Salva', delete: 'Elimina',
    edit: 'Modifica', view: 'Visualizza',
    common_back: 'Indietro', common_next: 'Avanti', common_search: 'Cerca',
    common_filter: 'Filtra', common_export: 'Esporta', common_import: 'Importa',
    common_refresh: 'Aggiorna', common_none: 'Nessuno', common_all: 'Tutti',
    common_yes: 'Sì', common_no: 'No', common_ok: 'OK', common_create: 'Crea',
    common_blocks: 'Blocchi', common_block: 'Blocco', common_wallet: 'Portafoglio',
    common_wallets: 'Portafogli', common_group: 'Gruppo', common_groups: 'Gruppi',
    common_members: 'Membri', common_pending: 'In attesa', common_active: 'Attivo',
    common_inactive: 'Inattivo',
    status_healthy: 'Sano', status_unhealthy: 'Non sano', status_pending: 'In attesa',
    status_completed: 'Completato', status_failed: 'Fallito',
    home_title: 'Home', home_alerts_debug: 'Avvisi DEBUG',
    home_kpi_pol: 'PoL', home_kpi_blocks: 'Blocchi', home_kpi_wallets: 'Portafogli',
    home_kpi_graphs: 'Grafici', home_kpi_chain: 'Catena', home_kpi_network: 'rete',
    home_chain_valid: 'VALIDA OK', home_chain_check: 'VERIFICA',
    home_checklist_title: 'Avvio rapido', home_checklist_memorize: 'Memorizza testo',
    home_checklist_explore: 'Esplora grafico', home_checklist_search: 'Cerca nodo',
    home_checklist_sign: 'Ricostruisci + firma blocco', home_checklist_goto: '→ Vai',
    home_demo_last: 'Ultimo demo_live:', home_demo_ok: 'OK OK',
    home_demo_not_found: 'non trovato', home_activity_heatmap: 'Attività blocchi (mappa calore)',
    home_latest_blocks: 'Ultimi blocchi', home_view_all: 'Vedi tutto →',
    home_reward_note: 'Ricompensa genesi: 1 ARTCB / blocco', home_ir_live: 'IR live',
    memorize_title: 'Memorizza', memorize_session: 'Sessione', memorize_session_id: 'session_id',
    memorize_use_llm: 'usa LLM', memorize_use_pool: 'calcolo distribuito (pool E2E)',
    memorize_encrypt_transport: 'ML-KEM cifrato (obbligatorio)',
    memorize_visibility_current: 'Visibilità attuale',
    memorize_select_group: 'seleziona gruppo in /groups',
    memorize_source_title: 'Fonte — griglia di sintesi',
    memorize_placeholder: 'Testo da memorizzare…', memorize_button: 'Memorizza',
    memorize_button_loading: 'Memorizzazione…', memorize_graph_title: 'Grafico in costruzione',
    memorize_graph_id: 'graph_id', memorize_nodes: 'nodi',
    memorize_sign_block: 'Firma blocco', memorize_sign_loading: 'Firma…',
    graph_title: 'Grafico', graph_title_with_id: 'Grafico ·',
    graph_no_graph: 'Nessun grafico — vai su Memorizza.',
    graph_selected: 'Selezionato', graph_search_placeholder: 'Cerca…',
    graph_search_button: 'Cerca', graph_tts_button: 'Leggi', graph_sign_button: 'Firma blocco',
    graph_found: 'Trovato', graph_error: 'Errore', graph_block_signed: 'Blocco firmato',
    wallets_title: 'Portafogli · forziere', wallets_create_title: 'Crea portafoglio',
    wallets_create_placeholder: 'Nome portafoglio', wallets_create_button: 'Genera',
    wallets_balance: 'Saldo', wallets_address: 'Indirizzo',
    wallets_founders_title: 'Allocazione fondatori', wallets_rewards_title: 'Ricompense',
    wallets_rewards_block: 'Blocco', wallets_rewards_amount: 'Ricompensa ₳',
    wallets_rewards_timestamp: 'Data', wallets_error: 'Errore',
    mining_title: 'Mining', mining_hero_title: 'Mining Prova-di-Apprendimento',
    mining_hero_subtitle: 'Epoca: {reward} ARTCB/blocco — no PoW',
    mining_epoch: 'Epoca', mining_kpi_pol_session: 'PoL sessione',
    mining_kpi_blocks_mined: 'Blocchi minati', mining_kpi_rewards_total: 'Ricompense totali',
    mining_kpi_halving: 'Halving tra', mining_kpi_halving_blocks: 'blocchi',
    mining_last_result_title: 'Ultimo risultato mining (file reale)',
    mining_last_result_pol: 'pol', mining_last_result_reversible: 'reversibile',
    mining_last_result_nodes: 'nodi', mining_last_result_reward: 'total_reward_artcb',
    mining_launch_hint: 'Avvia mining via', mining_real_scripts: 'script reali su macchina utente',
    system_title: 'Sistema · F3 Debug', system_f3_title: '[ F3 ] ARTCB SCHERMO DEBUG',
    system_cpu: 'CPU', system_cores: 'core', system_ram: 'RAM', system_disk: 'Disco',
    system_disk_free: 'GB liberi', system_network: 'Rete', system_hostname: 'Host',
    system_gpu_faiss: 'GPU / FAISS', system_gpu_none: 'Nessuna GPU CUDA rilevata',
    system_gpu_faiss_count: 'FAISS GPU', system_optimizations: 'Ottimizzazioni',
    system_workers: 'Worker', system_chunk_pool: 'Chunk pool', system_faiss: 'FAISS',
    system_physical_cores: 'fisici', system_logical_cores: 'logici',
    system_error_metrics: 'Errore metriche', system_loading_metrics: 'Caricamento metriche...',
    logs_title: 'Log · chat MC', logs_demo_title: 'demo_live_latest.txt',
    logs_demo_loading: 'Caricamento…', logs_rtleg_title: 'Eventi RT-LEG',
    logs_rtleg_error: 'Errore',
    console_title: 'Console CLI', console_hint: 'API completa — equivalente terminale',
    console_placeholder: 'help | health | pool status | p2p sync | mining status',
    console_execute: 'Esegui', console_unknown_command: 'Comando sconosciuto',
    console_type_help: 'Digita help', console_welcome: 'ARTCB Console v0.4 — digita help',
    agent_panel_title: 'Agenti duali', agent_panel_empty: 'Explorer e Critic commentano durante la codifica…',
    agent_explorer: 'Explorer', agent_critic: 'Critic',
    reconstruct_title: 'Ricostruzione', reconstruct_original: 'Originale',
    reconstruct_reconstructed: 'Ricostruito', reconstruct_ok: 'OK 100%',
    block_row_no_blocks: 'Nessun blocco',
    api_keys_title: 'Chiavi API · Accesso esterno', api_keys_token_warning: 'Copia questo token ora — non verrà mostrato di nuovo', api_keys_new_key: 'Nuova chiave API', api_keys_active: 'Chiavi attive', api_keys_cursor_usage: 'Come usare in Cursor',
    agent_memory_title: 'Memoria Agente — ARTCB IA', agent_memory_tab_status: 'Stato', agent_memory_tab_memos: 'Memo', agent_memory_tab_new: 'Nuovo memo', agent_memory_tab_search: 'Cerca', agent_memory_tab_export: 'Esporta', agent_memory_tab_webhooks: 'Webhooks', agent_memory_tab_stream: 'Stream',
  },

  ru: {
    nav_dashboard: 'Панель', nav_encode: 'Кодировать', nav_agents: 'Агенты',
    nav_chain: 'Цепь', nav_pol: 'PoL', nav_memorize: 'Запомнить',
    nav_graph: 'Граф', nav_wallets: 'Кошельки', nav_mining: 'Майнинг',
    nav_system: 'Система', nav_logs: 'Журналы', nav_console: 'Консоль',
    nav_integrations: 'Интеграции', nav_network: 'P2P сеть',
    nav_governance: 'Управление', nav_groups: 'Группы', nav_api_keys: 'API ключи', nav_agent_memory: 'Память ИИ',
    dashboard_title: 'Панель ARTCB', dashboard_subtitle: 'Децентрализованная коллективная память',
    dashboard_blocks: 'Блоки', dashboard_pol_score: 'Оценка PoL', dashboard_graphs: 'Графики',
    layout_visibility: 'Сеть', layout_visibility_private: 'ЧАСТНОЕ',
    layout_visibility_public: 'ПУБЛИЧНОЕ', layout_visibility_group: 'ГРУППА',
    layout_select_group: 'Выбрать группу', layout_no_group: 'Нет группы',
    layout_create_group_first: 'Сначала создайте группу', layout_select_wallet: 'Выбрать кошелёк',
    layout_no_wallet: 'Нет кошелька', layout_create_wallet_first: 'Сначала создайте кошелёк',
    layout_language: 'Язык',
    encode_title: 'Кодировать текст', encode_placeholder: 'Введите текст здесь...',
    encode_button: 'Кодировать', encode_success: 'Текст успешно закодирован',
    encode_error: 'Ошибка кодирования текста',
    agents_title: 'ИИ Агенты', agents_run: 'Запустить', agents_explorer: 'Исследователь',
    agents_critic: 'Критик', agents_status: 'Статус',
    chain_title: 'Блокчейн', chain_blocks: 'Блоки', chain_valid: 'Цепь действительна',
    chain_invalid: 'Цепь недействительна', chain_verify: 'Проверить',
    chain_block_detail: 'Детали блока', chain_back: '← назад',
    chain_timestamp: 'Временная метка', chain_hash: 'Хэш', chain_signature: 'Подпись',
    chain_reward: 'Награда', chain_contributors: 'Контрибуторы', chain_address: 'Адрес',
    chain_pol_score: 'Оценка PoL', chain_share: 'Доля', chain_height: 'Высота',
    chain_verification: 'Проверка', chain_epoch_reward: 'Награда эпохи',
    chain_recent_blocks: 'Последние блоки', chain_detailed_table: 'Подробная таблица',
    chain_index: 'Индекс', chain_visibility: 'Видимость', chain_graph_id: 'graph_id',
    pol_title: 'Доказательство обучения', pol_score: 'Оценка', pol_compression: 'Сжатие',
    pol_validation: 'Проверка', pol_retrieval: 'Извлечение',
    pol_gauge_title: 'Доказательство обучения', pol_gauge_accepted: 'Блок принят OK',
    pol_gauge_below_threshold: 'Ниже порога',
    loading: 'Загрузка...', error: 'Ошибка', success: 'Успех', cancel: 'Отмена',
    confirm: 'Подтвердить', close: 'Закрыть', save: 'Сохранить', delete: 'Удалить',
    edit: 'Редактировать', view: 'Просмотр',
    common_back: 'Назад', common_next: 'Далее', common_search: 'Поиск',
    common_filter: 'Фильтр', common_export: 'Экспорт', common_import: 'Импорт',
    common_refresh: 'Обновить', common_none: 'Нет', common_all: 'Все',
    common_yes: 'Да', common_no: 'Нет', common_ok: 'OK', common_create: 'Создать',
    common_blocks: 'Блоки', common_block: 'Блок', common_wallet: 'Кошелёк',
    common_wallets: 'Кошельки', common_group: 'Группа', common_groups: 'Группы',
    common_members: 'Участники', common_pending: 'Ожидание', common_active: 'Активный',
    common_inactive: 'Неактивный',
    status_healthy: 'Здоров', status_unhealthy: 'Нездоров', status_pending: 'Ожидание',
    status_completed: 'Завершено', status_failed: 'Не удалось',
    home_title: 'Главная', home_alerts_debug: 'Отладочные оповещения',
    home_kpi_pol: 'PoL', home_kpi_blocks: 'Блоки', home_kpi_wallets: 'Кошельки',
    home_kpi_graphs: 'Графики', home_kpi_chain: 'Цепь', home_kpi_network: 'сеть',
    home_chain_valid: 'VALID OK', home_chain_check: 'ПРОВЕРКА',
    home_checklist_title: 'Быстрый старт', home_checklist_memorize: 'Запомнить текст',
    home_checklist_explore: 'Исследовать граф', home_checklist_search: 'Найти узел',
    home_checklist_sign: 'Реконструировать + подписать блок', home_checklist_goto: '→ Перейти',
    home_demo_last: 'Последний demo_live:', home_demo_ok: 'OK OK',
    home_demo_not_found: 'не найдено', home_activity_heatmap: 'Активность блоков (тепловая карта)',
    home_latest_blocks: 'Последние блоки', home_view_all: 'Смотреть всё →',
    home_reward_note: 'Награда генезис: 1 ARTCB / блок', home_ir_live: 'IR в реальном времени',
    memorize_title: 'Запомнить', memorize_session: 'Сессия', memorize_session_id: 'session_id',
    memorize_use_llm: 'использовать LLM', memorize_use_pool: 'распределённые вычисления (pool E2E)',
    memorize_encrypt_transport: 'ML-KEM зашифровано (обязательно)',
    memorize_visibility_current: 'Текущая видимость',
    memorize_select_group: 'выберите группу в /groups',
    memorize_source_title: 'Источник — сетка синтеза',
    memorize_placeholder: 'Текст для запоминания…', memorize_button: 'Запомнить',
    memorize_button_loading: 'Запоминание…', memorize_graph_title: 'Граф строится',
    memorize_graph_id: 'graph_id', memorize_nodes: 'узлы',
    memorize_sign_block: 'Подписать блок', memorize_sign_loading: 'Подпись…',
    graph_title: 'Граф', graph_title_with_id: 'Граф ·',
    graph_no_graph: 'Нет графа — перейдите на Запомнить.',
    graph_selected: 'Выбрано', graph_search_placeholder: 'Поиск…',
    graph_search_button: 'Поиск', graph_tts_button: 'Читать', graph_sign_button: 'Подписать блок',
    graph_found: 'Найдено', graph_error: 'Ошибка', graph_block_signed: 'Блок подписан',
    wallets_title: 'Кошельки · сундук', wallets_create_title: 'Создать кошелёк',
    wallets_create_placeholder: 'Имя кошелька', wallets_create_button: 'Создать',
    wallets_balance: 'Баланс', wallets_address: 'Адрес',
    wallets_founders_title: 'Распределение основателей', wallets_rewards_title: 'Награды',
    wallets_rewards_block: 'Блок', wallets_rewards_amount: 'Награда ₳',
    wallets_rewards_timestamp: 'Дата', wallets_error: 'Ошибка',
    mining_title: 'Майнинг', mining_hero_title: 'Майнинг Доказательства-обучения',
    mining_hero_subtitle: 'Эпоха: {reward} ARTCB/блок — без PoW',
    mining_epoch: 'Эпоха', mining_kpi_pol_session: 'PoL сессия',
    mining_kpi_blocks_mined: 'Добыто блоков', mining_kpi_rewards_total: 'Всего наград',
    mining_kpi_halving: 'Халвинг через', mining_kpi_halving_blocks: 'блоков',
    mining_last_result_title: 'Последний результат майнинга (реальный файл)',
    mining_last_result_pol: 'pol', mining_last_result_reversible: 'обратимо',
    mining_last_result_nodes: 'узлы', mining_last_result_reward: 'total_reward_artcb',
    mining_launch_hint: 'Запустить майнинг через', mining_real_scripts: 'реальные скрипты на машине пользователя',
    system_title: 'Система · F3 Отладка', system_f3_title: '[ F3 ] ARTCB ЭКРАН ОТЛАДКИ',
    system_cpu: 'CPU', system_cores: 'ядра', system_ram: 'ОЗУ', system_disk: 'Диск',
    system_disk_free: 'ГБ свободно', system_network: 'Сеть', system_hostname: 'Хост',
    system_gpu_faiss: 'GPU / FAISS', system_gpu_none: 'GPU CUDA не обнаружена',
    system_gpu_faiss_count: 'FAISS GPUs', system_optimizations: 'Оптимизации',
    system_workers: 'Воркеры', system_chunk_pool: 'Чанк пул', system_faiss: 'FAISS',
    system_physical_cores: 'физических', system_logical_cores: 'логических',
    system_error_metrics: 'Ошибка метрик', system_loading_metrics: 'Загрузка метрик...',
    logs_title: 'Журналы · MC чат', logs_demo_title: 'demo_live_latest.txt',
    logs_demo_loading: 'Загрузка…', logs_rtleg_title: 'RT-LEG события',
    logs_rtleg_error: 'Ошибка',
    console_title: 'CLI Консоль', console_hint: 'Полный API — эквивалент терминала',
    console_placeholder: 'help | health | pool status | p2p sync | mining status',
    console_execute: 'Выполнить', console_unknown_command: 'Неизвестная команда',
    console_type_help: 'Введите help', console_welcome: 'ARTCB Консоль v0.4 — введите help',
    agent_panel_title: 'Двойные агенты', agent_panel_empty: 'Explorer и Critic комментируют во время кодирования…',
    agent_explorer: 'Explorer', agent_critic: 'Critic',
    reconstruct_title: 'Реконструкция', reconstruct_original: 'Оригинал',
    reconstruct_reconstructed: 'Реконструировано', reconstruct_ok: 'OK 100%',
    block_row_no_blocks: 'Нет блоков',
    api_keys_title: 'API ключи · Внешний доступ', api_keys_token_warning: 'Скопируйте этот токен сейчас — он не будет показан снова', api_keys_new_key: 'Новый API ключ', api_keys_active: 'Активные ключи', api_keys_cursor_usage: 'Как использовать в Cursor',
    agent_memory_title: 'Память агента — ARTCB ИИ', agent_memory_tab_status: 'Статус', agent_memory_tab_memos: 'Заметки', agent_memory_tab_new: 'Новая заметка', agent_memory_tab_search: 'Поиск', agent_memory_tab_export: 'Экспорт', agent_memory_tab_webhooks: 'Webhooks', agent_memory_tab_stream: 'Поток',
  },
};

export function getTranslation(lang: Language, key: keyof Translations): string {
  return (translations[lang][key] as string | undefined) || (translations.en[key] as string | undefined) || (translations.fr[key] as string) || key;
}

export function getCurrentLanguage(): Language {
  const stored = localStorage.getItem('artcb_language');
  if (stored && stored in translations) {
    return stored as Language;
  }
  
  const browserLang = navigator.language.split('-')[0];
  if (browserLang in translations) {
    return browserLang as Language;
  }
  
  return 'en';
}

export function setLanguage(lang: Language): void {
  localStorage.setItem('artcb_language', lang);
  window.dispatchEvent(new Event('languagechange'));
}

