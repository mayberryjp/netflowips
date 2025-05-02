VERSION="v0.1.7"
CONST_COLLECTOR_LISTEN_PORT=2055
CONST_COLLECTOR_LISTEN_ADDRESS="0.0.0.0"
CONST_API_LISTEN_PORT=8044
CONST_API_LISTEN_ADDRESS="0.0.0.0"
IS_CONTAINER=1
CONST_NEWFLOWS_DB="/database/newflows.db"
CONST_ALLFLOWS_DB="/database/allflows.db"
CONST_LOCALHOSTS_DB = "/database/localhosts.db"
CONST_DNSQUERIES_DB = '/database/dnsqueries.db'
CONST_CONFIG_DB="/database/config.db"
CONST_ALERTS_DB="/database/alerts.db"
CONST_WHITELIST_DB = '/database/whitelist.db'
#CONST_TEST_SOURCE_DB = ['/database/test_source_1.db','/database/test_source_2.db']
CONST_TEST_SOURCE_DB = ['/database/test_source_2.db']
CONST_GEOLOCATION_DB = '/database/geolocation.db'
CONST_SITE= 'TEST'
CONST_REINITIALIZE_DB = 0
CONST_CREATE_NEWFLOWS_SQL='''
    CREATE TABLE IF NOT EXISTS flows (
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
        last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
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
        first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        acknowledged INTEGER DEFAULT 0
    )'''

CONST_CREATE_WHITELIST_SQL='''
    CREATE TABLE IF NOT EXISTS whitelist (
        whitelist_id TEXT PRIMARY KEY,
        whitelist_src_ip TEXT,
        whitelist_dst_ip TEXT,
        whitelist_dst_port INTEGER,
        whitelist_protocol INTEGER,
        whitelist_insert_date TEXT DEFAULT CURRENT_TIMESTAMP,
        whitelist_enabled INTEGER DEFAULT 1,
        whitelist_description TEXT,
        whitelist_added TEXT DEFAULT CURRENT_TIMESTAMP
    )'''

CONST_CREATE_CONFIG_SQL='''
    CREATE TABLE IF NOT EXISTS configuration (
        key TEXT PRIMARY KEY,
        value INTEGER
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
        import_date TEXT DEFAULT CURRENT_TIMESTAMP
    )
'''

CONST_CREATE_PIHOLE_SQL = '''
    CREATE TABLE IF NOT EXISTS pihole (
        client_ip TEXT,
        times_seen INTEGER DEFAULT 0,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        type TEXT,
        domain TEXT,
        PRIMARY KEY (client_ip, domain, type)
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
    ('WhitelistEntries', ''),
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
    ('ReputationListRemove','192.168.0.0/16,0.0.0.0/8,224.0.0.0/3'),
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
    ('IntegrationFetchInterval',3660),
    ('TorFlowDetection','0'),
    ('TorNodesUrl','https://www.dan.me.uk/torlist/?full'),
    ('HighBandwidthFlowDetection','0'),
    ('MaxPackets',30000),
    ('MaxBytes',3000000),
    ('StorePiHoleDnsQueryHistory','0'),
    ('SendDeviceClassificationsToHomelabApi','0')
]