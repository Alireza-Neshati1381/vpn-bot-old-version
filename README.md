# VPN Bot - Telegram VPN Subscription Management

A full-featured Telegram bot for selling and managing VPN subscriptions with bilingual support (Persian/Farsi and English).

## Features

### Core Capabilities
- **Bilingual UI**: Full support for Persian (Farsi) and English with user-selectable language
- **Role-based Access Control**: Admin, Accountant, and User roles with appropriate permissions
- **Two Package Models**:
  - **Prebuilt Packages**: Admin-defined packages with fixed pricing
  - **Per-GB Pricing**: Dynamic pricing based on volume, duration, and concurrent users
- **Multi-Server Support**: Manage multiple VPN servers and create packages spanning multiple servers
- **Order Management**: Complete order lifecycle from creation to approval
- **Receipt Upload**: Users upload payment receipts for accountant review
- **VPN Provisioning**: Automatic integration with 3x-ui panel API

### Security Features
- Admin PIN authentication (no hardcoded credentials)
- Rate limiting per user (configurable)
- Input validation and sanitization
- Secure file handling for receipt uploads
- Security event logging
- Prepared statements to prevent SQL injection

## Project Structure

```
VPN-Bot/
├── main.py                 # Application entrypoint
├── requirements.txt        # Python dependencies
├── migrations/            # Database migration scripts
│   └── 001_initial_schema.sql
├── translations/          # i18n translation files
│   ├── en.json           # English translations
│   └── fa.json           # Persian translations
├── vpn_bot/              # Main application package
│   ├── __init__.py
│   ├── config.py         # Configuration loader
│   ├── database.py       # Database helpers
│   ├── handlers.py       # Bot logic and handlers
│   ├── telegram.py       # Telegram API client
│   ├── xui_api.py        # 3x-ui panel API client
│   ├── scheduler.py      # Background expiration worker
│   ├── i18n.py           # Internationalization system
│   ├── security.py       # Security utilities
│   └── pricing.py        # Price calculation engine
└── tests/                 # Test suite
    ├── test_pricing.py
    ├── test_i18n.py
    └── test_api.py
```

## Environment Variables

Create a `.env` file in the `VPN-Bot/` directory or set these environment variables:

### Required Variables

```bash
# Telegram Bot Token (get from @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Admin PIN for authentication (set a strong PIN)
BOT_ADMIN_PIN=your_secure_admin_pin
```

### Optional Variables

```bash
# Database
DB_PATH=vpn_bot.sqlite3

# API Settings
XUI_VERIFY_SSL=false
POLL_INTERVAL=1.0

# Security
RATE_LIMIT_PER_MIN=20
MAX_RECEIPT_SIZE_MB=5

# Receipt Storage
RECEIPT_STORAGE=local
RECEIPT_UPLOAD_DIR=uploads/receipts

# Localization
DEFAULT_LANGUAGE=fa

# Logging
LOG_LEVEL=INFO
```

See `VPN-Bot/.env.example` for a complete template.

## Installation & Setup

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/Alireza-Neshati1381/vpn-bot-old-version.git
   cd vpn-bot-old-version/VPN-Bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and set required variables (TELEGRAM_BOT_TOKEN and BOT_ADMIN_PIN are required)
   ```

4. **Run database migrations**
   ```bash
   sqlite3 vpn_bot.sqlite3 < migrations/001_initial_schema.sql
   ```

5. **Start the bot**
   ```bash
   python main.py
   ```

### Docker Deployment

1. **Build the image**
   ```bash
   docker build -t vpn-bot .
   ```

2. **Run with docker-compose**
   ```bash
   docker-compose up -d
   ```

## Usage Guide

### First-Time Setup

1. Start the bot with `/start` - the first user becomes Admin automatically
2. Admin should immediately set the admin PIN (via environment variable)
3. Add servers using "Add Server" button
4. Add inbounds for each server
5. Create packages (prebuilt or configure per-GB pricing)
6. Assign accountant role to users who will review receipts

### Admin Workflows

#### Add a Server
1. Click "Add Server"
2. Send: `Title,URL,Username,Password`
3. Example: `Germany Server,https://panel.example.com,admin,secretpass`

#### Add an Inbound
1. Click "Add Inbound"
2. Send: `InboundID,FriendlyName`
3. Example: `1,Main Inbound`

#### Create Prebuilt Package
1. Click "Add Plan"
2. Choose "Prebuilt Package"
3. Send plan data: `Name,ServerID,InboundID,Country,VolumeGB,DurationDays,MultiUser,Price`
4. Example: `Premium,1,1,DE,100,30,1,10.00`

#### Configure Per-GB Pricing
1. Click "Pricing Settings"
2. Choose server or "Apply to All"
3. Set: price per GB, min/max months, extra user pricing

### Accountant Workflows

1. Click "Pending Receipts" to see orders awaiting review
2. View receipt images
3. Click "Approve" or "Reject" for each order
4. On approval, VPN config is automatically provisioned

### Customer Workflows

#### Purchase Prebuilt Plan
1. Click "Buy Plan"
2. Select desired plan
3. Make payment to provided bank card
4. Upload payment receipt photo
5. Wait for accountant approval
6. Receive VPN configuration

#### Customize Plan (Per-GB Pricing)
1. Click "Customize Plan"
2. Select server
3. Choose volume (GB)
4. Choose duration (months)
5. Choose number of users
6. Review price breakdown
7. Confirm order
8. Upload receipt and wait for approval

## API Integration

This bot integrates with the 3x-ui panel API. The implementation matches the official Postman collection.

### API Endpoints Used

| Bot Action | API Endpoint | Method | Description |
|-----------|-------------|--------|-------------|
| Login | `/login/` | POST | Authenticate with panel |
| Add Client | `/panel/api/inbounds/addClient` | POST | Create VPN config |
| Remove Client | `/panel/api/inbounds/delClient` | POST | Remove expired config |
| Get Inbound | `/panel/api/inbounds/get/{id}` | GET | Fetch inbound details |
| Get Traffic | `/panel/api/inbounds/getClientTraffics/{id}` | GET | Check usage stats |

### API Authentication

The bot uses session-based authentication with cookies (not bearer tokens). This matches the 3x-ui panel's actual authentication mechanism.

See `vpn_bot/xui_api.py` for the complete implementation.

## Testing

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=vpn_bot --cov-report=html

# Run specific test file
pytest tests/test_pricing.py
```

### Manual Testing

Use the provided test script:

```bash
python tests/manual_test.py
```

This script:
1. Creates test admin user
2. Creates test server and plan
3. Places test order
4. Simulates approval workflow

## Security Considerations

### Implemented Security Measures

- ✅ Environment variable configuration (no hardcoded secrets)
- ✅ Admin PIN authentication
- ✅ Role-based access control
- ✅ Input validation and sanitization
- ✅ Rate limiting per user
- ✅ Secure file handling for receipts
- ✅ SQL injection prevention (parameterized queries)
- ✅ Security event logging
- ✅ TLS for API calls (with optional verification)

### Recommended Additional Hardening

- [ ] Enable 2FA for admin accounts (external OAuth)
- [ ] Deploy behind WAF (Web Application Firewall)
- [ ] Configure firewall rules to restrict panel access
- [ ] Use HSM or secrets manager for sensitive credentials
- [ ] Enable SSL certificate verification in production (`XUI_VERIFY_SSL=true`)
- [ ] Regular security audits and dependency updates
- [ ] Implement IP whitelisting for panel access
- [ ] Set up monitoring and alerting for suspicious activity

## Database Schema

The bot uses SQLite by default (easily portable to PostgreSQL).

### Main Tables

- `users` - Telegram users with roles and language preferences
- `servers` - VPN panel server connections
- `inbounds` - Inbound configurations from panels
- `plans` - VPN subscription packages
- `plan_servers` - Many-to-many relationship for multi-server packages
- `server_pricing` - Per-GB pricing configuration
- `orders` - Customer orders and provisioning status
- `settings` - Bot configuration (bank card, etc.)
- `security_events` - Audit log

See `migrations/001_initial_schema.sql` for the complete schema.

## Troubleshooting

### Bot doesn't respond
- Check `TELEGRAM_BOT_TOKEN` is correct
- Verify bot is running: `ps aux | grep python`
- Check logs for errors

### API calls fail
- Verify `XUI_VERIFY_SSL` setting matches your panel
- Check server credentials in database
- Test panel access manually with curl
- Review logs for detailed error messages

### Receipt uploads fail
- Check `RECEIPT_UPLOAD_DIR` exists and is writable
- Verify `MAX_RECEIPT_SIZE_MB` is sufficient
- Ensure disk space is available

### Database errors
- Run migrations: `sqlite3 vpn_bot.sqlite3 < migrations/001_initial_schema.sql`
- Check file permissions on database file
- Verify disk space

## Development

### Code Style

This project follows PEP 8 with these tools:
- `black` for formatting
- `flake8` for linting

Run before committing:
```bash
black vpn_bot/
flake8 vpn_bot/
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run tests and linting
6. Submit a pull request

## License

This project is provided as-is for educational and commercial use.

## Support

For issues and questions:
- Open an issue on GitHub
- Check existing issues for solutions
- Review logs for error details

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and changes.
