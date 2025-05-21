VERSION="v0.3.98"
# v3 is after consolidating database, v4 is moving to ORM, v5 is moving to constructor, v6 is integrating agent
CONST_COLLECTOR_LISTEN_PORT=2055
CONST_COLLECTOR_LISTEN_ADDRESS="0.0.0.0"
CONST_API_LISTEN_PORT=8044
CONST_API_LISTEN_ADDRESS="0.0.0.0"
IS_CONTAINER=1
CONST_CONSOLIDATED_DB = "/database/consolidated.db"
#CONST_TEST_SOURCE_DB = ['/database/test_source_1.db','/database/test_source_2.db']
CONST_TEST_SOURCE_DB = ['/database/test_source_1.db']
CONST_SITE= 'TESTPPE'
CONST_LINK_LOCAL_RANGE = ["169.254.0.0/16"]
CONST_REINITIALIZE_DB = 0
CONST_CREATE_NEWFLOWS_SQL='''
    CREATE TABLE IF NOT EXISTS newflows (
        src_ip TEXT,
        dst_ip TEXT,
        src_port INTEGER,
        dst_port INTEGER,
        protocol INTEGER,
        packets INTEGER,
        bytes INTEGER,
        flow_start TEXT,
        flow_end TEXT,
        last_seen TEXT,
        times_seen INTEGER,
        tags TEXT,
        PRIMARY KEY (src_ip, dst_ip, src_port, dst_port, protocol)
    )'''

CONST_CREATE_SERVICES_SQL="""
    CREATE TABLE IF NOT EXISTS services (
        port_number INTEGER,
        protocol TEXT,
        service_name TEXT,
        description TEXT,
        PRIMARY KEY (port_number, protocol)
    )"""

CONST_CREATE_ALLFLOWS_SQL='''
    CREATE TABLE IF NOT EXISTS allflows (
        src_ip TEXT,
        dst_ip TEXT,
        src_port INTEGER,
        dst_port INTEGER,
        protocol INTEGER,
        packets INTEGER,
        bytes INTEGER,
        flow_start TEXT,
        flow_end TEXT,
        times_seen INTEGER DEFAULT 1,
        last_seen TEXT,
        tags TEXT,
        PRIMARY KEY (src_ip, dst_ip, src_port, dst_port, protocol)
    )'''

CONST_CREATE_ALERTS_SQL='''
    CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,  -- Primary key based on concatenating ip_address and category
        ip_address TEXT,
        flow TEXT,
        category TEXT,
        alert_enrichment_1 TEXT,
        alert_enrichment_2 TEXT,
        times_seen INTEGER DEFAULT 0,
        first_seen TEXT,
        last_seen TEXT,
        acknowledged INTEGER DEFAULT 0
    )
'''

CONST_CREATE_IGNORELIST_SQL='''
    CREATE TABLE IF NOT EXISTS ignorelist (
        ignorelist_id TEXT PRIMARY KEY,
        ignorelist_src_ip TEXT,
        ignorelist_dst_ip TEXT,
        ignorelist_dst_port INTEGER,
        ignorelist_protocol INTEGER,
        ignorelist_insert_date TEXT,
        ignorelist_enabled INTEGER DEFAULT 1,
        ignorelist_description TEXT,
        ignorelist_added TEXT
    )'''

CONST_CREATE_CUSTOMTAGS_SQL='''
    CREATE TABLE IF NOT EXISTS customtags (
        tag_id TEXT PRIMARY KEY,
        src_ip TEXT,
        dst_ip TEXT,
        dst_port INTEGER,
        protocol TEXT,
        tag_name TEXT,
        enabled INTEGER DEFAULT 1,
        added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        insert_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )'''

CONST_CREATE_CONFIG_SQL='''
    CREATE TABLE IF NOT EXISTS configuration (
        key TEXT PRIMARY KEY,
        value INT,
        last_changed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )'''

CONST_CREATE_GEOLOCATION_SQL="""
    CREATE TABLE IF NOT EXISTS geolocation (
        network TEXT PRIMARY KEY,
        start_ip INTEGER,
        end_ip INTEGER,
        netmask INTEGER,
        country_name TEXT
    )"""

CONST_CREATE_LOCALHOSTS_SQL = """
    CREATE TABLE IF NOT EXISTS localhosts (
        ip_address TEXT PRIMARY KEY,
        first_seen TEXT,
        original_flow TEXT,
        mac_address TEXT,
        mac_vendor TEXT,
        dhcp_hostname TEXT,
        dns_hostname TEXT,
        os_fingerprint TEXT,
        local_description TEXT,
        lease_hostname TEXT,
        lease_hwaddr TEXT,
        lease_clientid TEXT,
        icon TEXT,                -- New column for icon
        tags TEXT,                -- New column for tags
        acknowledged INTEGER DEFAULT 0 -- New column for acknowledged
    )
"""

CONST_CREATE_IPASN_SQL="""
        CREATE TABLE IF NOT EXISTS asn (
            network TEXT PRIMARY KEY,
            start_ip INTEGER,
            end_ip INTEGER,
            netmask INTEGER,
            asn TEXT,
            isp_name TEXT
        )
    """

CONST_CREATE_TRAFFICSTATS_SQL = """
    CREATE TABLE IF NOT EXISTS trafficstats (
        ip_address TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        total_packets INTEGER DEFAULT 0,
        total_bytes INTEGER DEFAULT 0,
        PRIMARY KEY (ip_address, timestamp)
    )"""

CONST_CREATE_REPUTATIONLIST_SQL="""
    CREATE TABLE IF NOT EXISTS reputationlist (
        network TEXT PRIMARY KEY,
        start_ip INTEGER,
        end_ip INTEGER,
        netmask INTEGER
    )
"""

CONST_CREATE_TORNODES_SQL = '''
    CREATE TABLE IF NOT EXISTS tornodes (
        ip_address TEXT PRIMARY KEY,
        import_date TEXT
    )
'''

CONST_CREATE_PIHOLE_SQL = '''
    CREATE TABLE IF NOT EXISTS pihole (
        client_ip TEXT,
        times_seen INTEGER DEFAULT 0,
        last_seen TEXT,
        first_seen TEXT,
        type TEXT,
        domain TEXT,
        PRIMARY KEY (client_ip, domain, type)
    )
'''

CONST_CREATE_ACTIONS_SQL = '''
    CREATE TABLE IF NOT EXISTS actions (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_text TEXT,
    acknowledged INTEGER DEFAULT 0,
    insert_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''

CONST_INSTALL_CONFIGS = [
    ('NewHostsDetection', 0),
    ('LocalFlowsDetection', 0),
    ('RouterFlowsDetection', 0),
    ('ForeignFlowsDetection', 0),
    ('NewOutboundDetection', 0),
    ('GeolocationFlowsDetection', 0),
    ('BypassLocalDnsDetection', 0),
    ('IncorrectAuthoritativeDnsDetection', 0),
    ('BypassLocalNtpDetection', 0),
    ('IncorrectNtpStratrumDetection', 0),
    ('ApprovedLocalNtpServersList',''),
    ('ApprovedLocalDnsServersList',''),
    ('ApprovedAuthoritativeDnsServersList',''),
    ('ApprovedNtpStratumServersList',''),
    ('BannedCountryList','China,North Korea,Iran,Russia,Ukraine,Georgia,Armenia,Azerbaijan,Belarus,Syria,Venezuela,Cuba,Myanmar,Afghanistan'),
    ('LocalNetworks',''),
    ('RouterIpAddresses',''),
    ('ProcessingInterval','60'),
    ('TelegramBotToken',''),
    ('TelegramChatId',''),
    ('ScheduleProcessor','0'),
    ('StartCollector','1'),
    ('CleanNewFlows','0'),
    ('DeadConnectionDetection','0'),
    ('IgnoreListEntries', ''),
    ('DnsResolverTimeout', 3),
    ('DnsResolverRetries', 1),
    ('PiholeUrl', 'http://192.168.49.80/api'),
    ('PiholeApiKey',''),
    ('DiscoveryReverseDns', '0'),
    ('DiscoveryPiholeDhcp', '0'),
    ('EnableLocalDiscoveryProcess', '0'),
    ('DiscoveryProcessRunInterval', '60'),
    ('DiscoveryNmapOsFingerprint',0),
    ('ReputationUrl','https://iplists.firehol.org/files/firehol_level1.netset'),
    ('ReputationListRemove','192.168.0.0/16,0.0.0.0/8,224.0.0.0/3,169.254.0.0/16'),
    ('ReputationListDetection','0'),
    ('VpnTrafficDetection','0'),
    ('ApprovedVpnServersList',''),
    ('RemoveBroadcastFlows',1),
    ('HighRiskPortDetection','0'),
    ('HighRiskPorts','135,137,138,139,445,25,587,22,23,3389'),
    ('MaxUniqueDestinations','30'),
    ('ManyDestinationsDetection','0'),
    ('MaxPortsPerDestination','15'),
    ('PortScanDetection','0'),
    ('IntegrationFetchInterval',86400),
    ('TorFlowDetection','0'),
    ('TorNodesUrl','https://www.dan.me.uk/torlist/?full'),
    ('HighBandwidthFlowDetection','0'),
    ('MaxPackets',30000),
    ('MaxBytes',3000000),
    ('StorePiHoleDnsQueryHistory','0'),
    ('SendDeviceClassificationsToHomelabApi','0'),
    ('CollectorProcessingInterval','60'),
    ('SendErrorsToCloudApi','0'),
    ('RemoveMulticastFlows','1'),
    ('TagEntries', ''),
    ('AlertOnCustomTagList',''),
    ('AlertOnCustomTags','0'),
    ('SendConfigurationToCloudApi','0'),
    ('ApprovedHighRiskDestinations', ''),
    ('IgnoreListEntries', '[]'),
    ('MaxMindAPIKey', ''),
    ('RemoveLinkLocalFlows', '0'),
    ('ImportServicesList','1')
]