VERSION="v0.0.33"
CONST_LISTEN_PORT=2055
CONST_LISTEN_ADDRESS="0.0.0.0"
CONST_LOCAL_NETWORKS="192.168.48.0/22"
CONST_PROCESSING_INTERVAL=60
CONST_ROUTER_IPADDRESS="192.168.49.1"
IS_CONTAINER=1
CONST_NEWFLOWS_DB="/database/newflows.db"
CONST_ALLFLOWS_DB="/database/allflows.db"
CONST_LOCALHOSTS_DB = "/database/localhosts.db"
CONST_CONFIG_DB="/database/config.db"
CONST_ALERTS_DB="/database/alerts.db"
CONST_WHITELIST_DB = '/database/whitelist.db'
CONST_GEOLOCATION_DB = '/database/geolocation.db'
CONST_SITE= 'homelab'
CONST_REINITIALIZE_DB = 1
CONST_CLEAN_NEWFLOWS = 0
CONST_START_COLLECTOR = 1
CONST_SCHEDULE_PROCESSOR = 0
CONST_DEFAULT_CONFIGS = [
    ('NewHostsDetection', 1),
    ('LocalFlowsDetection', 1),
    ('RouterFlowsDetection', 0),
    ('ForeignFlowsDetection', 1),
    ('NewOutboundDetection', 1),
    ('GeolocationFlowsDetection', 1),
    ('BypassLocalDnsDetection', 0),
    ('IncorrectAuthoritativeDnsDetection', 0),
    ('BypassLocalNtpDetection', 0),
    ('IncorrectNtpStratrumDetection', 0),
    ('ApprovedLocalNtpServersList','192.168.230.236,192.168.49.80'),
    ('ApprovedLocalDnsServersList','192.168.230.236,192.168.49.80'),
    ('ApprovedAuthoritativeDnsServersList','8.8.8.8,8.8.4.4,1.1.1.1,1.0.0.1'),
    ('ApprovedNtpStratumServersList','162.159.200.123,162.159.200.123,216.239.35.0,216.239.35.4'),
    ('BannedCountryList','China,North Korea,Iran,Russia,Ukraine,Georgia,Armenia,Azerbaijan,Belarus,Syria,Venezuela,Cuba,Myanmar,Afghanistan'),
    # Add more default configurations here as needed
]
# Telegram Bot Configuration
CONST_TELEGRAM_BOT_TOKEN = ""  # Replace with your Telegram bot token
CONST_TELEGRAM_CHAT_ID = ""      # Replace with your Telegram group chat ID
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
        last_seen TEXT DEFAULT CURRENT_TIMESTAMP
    )'''

CONST_CREATE_WHITELIST_SQL='''
    CREATE TABLE IF NOT EXISTS whitelist (
        whitelist_id TEXT PRIMARY KEY,
        src_ip TEXT,
        dst_ip TEXT,
        dst_port INTEGER,
        protocol INTEGER,
        insert_date TEXT DEFAULT CURRENT_TIMESTAMP
        enabled INTEGER DEFAULT 1,
        description TEXT
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
