VERSION="v0.0.28"
CONST_LISTEN_PORT=2055
CONST_LISTEN_ADDRESS="0.0.0.0"
CONST_LOCAL_HOSTS="192.168.48.0/22"
CONST_PROCESSING_INTERVAL=60
MAXMIND_LICENSE_KEY="YOUR_MAXMIND_LICENSE_KEY"
MAXMIND_URL = f"https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City-CSV&license_key={MAXMIND_LICENSE_KEY}&suffix=tar.gz"
CONST_ROUTER_IPADDRESS="192.168.49.1"
IS_CONTAINER=1
CONST_NEWFLOWS_DB="/database/newflows.db"
CONST_ALLFLOWS_DB="/database/allflows.db"
CONST_LOCALHOSTS_DB = "/database/localhosts.db"
CONST_CONFIG_DB="/database/config.db"
CONST_ALERTS_DB="/database/alerts.db"
CONST_WHITELIST_DB = '/database/whitelist.db'
CONST_SITE= 'homelab'
CONST_DEFAULT_CONFIGS = [
    ('NewHostsDetection', 2),
    ('LocalFlowsDetection', 1),
    ('RouterFlowsDetection', 0),
    ('ForeignFlowsDetection', 1),
    ('NewOutboundDetection', 1),
    ('GeolocationFlowsDetection', 1),
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
        times_seen INTEGER DEFAULT 0,
        first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        last_seen TEXT DEFAULT CURRENT_TIMESTAMP
    )'''

CONST_CREATE_WHITELIST_SQL='''
    CREATE TABLE IF NOT EXISTS whitelist (
        whitelist_id TEXT PRIMARY KEY,
        insert_date TEXT DEFAULT CURRENT_TIMESTAMP
    )'''

CONST_CREATE_CONFIG_SQL='''
    CREATE TABLE IF NOT EXISTS configuration (
        key TEXT PRIMARY KEY,
        value INTEGER
    )'''


