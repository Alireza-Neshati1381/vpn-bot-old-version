# API Endpoint Mapping

This document maps bot actions to the 3x-ui panel API endpoints as defined in the Postman collection.

## Authentication

The bot uses session-based authentication with cookies, not bearer tokens.

### Login
**Bot Action**: Initial connection to panel  
**API Endpoint**: `POST /login/`  
**Implementation**: `xui_api.py` - `XUIClient._login()`  
**Request Body**:
```json
{
  "username": "admin",
  "password": "secret"
}
```
**Response**:
```json
{
  "success": true,
  "msg": "Successfully logged in"
}
```
**Notes**: 
- Sets session cookies for subsequent requests
- Automatically retries on 401 errors

## Client Management

### Create Client (Add VPN Config)
**Bot Action**: Approve order and provision VPN account  
**API Endpoint**: `POST /panel/api/inbounds/addClient`  
**Implementation**: `xui_api.py` - `XUIClient.create_client()`  
**Request Body**:
```json
{
  "id": 1,
  "settings": "{\"clients\":[{\"id\":\"uuid-here\",\"flow\":\"\",\"email\":\"order-123\",\"limitIp\":1,\"totalGB\":107374182400,\"expiryTime\":1704067200000,\"enable\":true,\"tgId\":\"\",\"subId\":\"abc123\",\"reset\":0}]}"
}
```
**Response**:
```json
{
  "success": true,
  "msg": "Client added",
  "obj": {
    "id": "uuid-here",
    "email": "order-123"
  }
}
```
**Notes**:
- `id` is the inbound ID (not client ID)
- `settings` must be a JSON string (double-encoded)
- `totalGB` is in bytes
- `expiryTime` is in milliseconds (timestamp * 1000)
- `limitIp` controls concurrent connections

### Remove Client (Expire VPN Config)
**Bot Action**: Remove expired VPN configuration  
**API Endpoint**: `POST /panel/api/inbounds/delClient`  
**Implementation**: `xui_api.py` - `XUIClient.remove_client()`  
**Request Body**:
```json
{
  "id": 1,
  "clientIds": ["uuid-here"]
}
```
**Response**:
```json
{
  "success": true,
  "msg": "Client deleted"
}
```
**Notes**:
- Can delete multiple clients at once via `clientIds` array

### Get Inbound Details
**Bot Action**: Build configuration link for user  
**API Endpoint**: `GET /panel/api/inbounds/get/{inbound_id}`  
**Implementation**: `xui_api.py` - `XUIClient.get_inbound()`  
**Response**:
```json
{
  "success": true,
  "obj": {
    "id": 1,
    "remark": "Main Inbound",
    "protocol": "vless",
    "port": 443,
    "listen": "0.0.0.0",
    "settings": "{\"clients\":[...],\"decryption\":\"none\"}",
    "streamSettings": "{\"network\":\"ws\",\"security\":\"tls\",\"tlsSettings\":{...},\"wsSettings\":{...}}"
  }
}
```
**Notes**:
- `settings` and `streamSettings` are JSON strings (need parsing)
- Used to extract TLS, network, and client details
- Required for generating vless://, vmess://, or trojan:// links

### Get Client Traffic Stats
**Bot Action**: Check data usage (background worker)  
**API Endpoint**: `GET /panel/api/inbounds/getClientTraffics/{inbound_id}?clientId={client_id}`  
**Implementation**: `xui_api.py` - `XUIClient.get_client_traffic()`  
**Response**:
```json
{
  "success": true,
  "obj": {
    "id": "uuid-here",
    "inboundId": 1,
    "email": "order-123",
    "enable": true,
    "up": 1073741824,
    "down": 10737418240,
    "total": 107374182400,
    "expiryTime": 1704067200000
  }
}
```
**Notes**:
- `up` and `down` are in bytes
- `total` is the limit in bytes
- Used to monitor usage and enforce limits

## Bot to API Flow Examples

### Order Approval Flow

1. **Accountant clicks "Approve"**
   ```
   Bot: handlers.py - _approve_order()
   ```

2. **Get plan and server details**
   ```sql
   SELECT * FROM plans WHERE id = ?
   SELECT * FROM servers WHERE id = ?
   ```

3. **Create XUI client**
   ```python
   client = XUIClient(server_url, username, password)
   client.create_client(inbound_id, config_payload)
   ```
   **API Call**: `POST /panel/api/inbounds/addClient`

4. **Get inbound details**
   ```python
   inbound_data = client.get_inbound(inbound_id)
   ```
   **API Call**: `GET /panel/api/inbounds/get/{id}`

5. **Build config link**
   ```python
   config_link = build_config_link(server_url, inbound_data, client_data)
   ```
   **Result**: `vless://uuid@host:port?type=ws&security=tls...#VPN`

6. **Send to user**
   ```python
   bot.send_message(user_telegram_id, f"Config: {config_link}")
   ```

### Expiration Worker Flow

1. **Background thread checks for expired orders**
   ```sql
   SELECT * FROM orders 
   WHERE status = 'ACTIVE' 
   AND expires_at <= datetime('now')
   ```

2. **For each expired order**
   ```python
   client = XUIClient(...)
   client.remove_client(inbound_id, client_id)
   ```
   **API Call**: `POST /panel/api/inbounds/delClient`

3. **Update database**
   ```sql
   UPDATE orders SET status = 'EXPIRED' WHERE id = ?
   ```

4. **Notify user**
   ```python
   bot.send_message(user_id, "Your VPN expired")
   ```

## Error Handling

### Session Expiry (401)
**Behavior**: Automatically re-authenticates and retries once
**Implementation**: `xui_api.py` - `_request()` method with `retry=True`

### Panel Unreachable
**Behavior**: Raises `XUIError`, logged and shown to admin
**Recovery**: Manual retry or check panel status

### Invalid Credentials
**Behavior**: Raises `XUIError` on login
**Recovery**: Admin must update server credentials in database

## Testing the API

### Manual Testing with curl

```bash
# Login
curl -X POST https://panel.example.com/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"secret"}' \
  -c cookies.txt

# Add client
curl -X POST https://panel.example.com/panel/api/inbounds/addClient \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"id":1,"settings":"{\"clients\":[{\"id\":\"test-uuid\",\"email\":\"test@example.com\",\"enable\":true}]}"}'

# Get inbound
curl -X GET https://panel.example.com/panel/api/inbounds/get/1 \
  -b cookies.txt

# Delete client
curl -X POST https://panel.example.com/panel/api/inbounds/delClient \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"id":1,"clientIds":["test-uuid"]}'
```

### Postman Collection Reference

The bot implementation is based on the official 3x-ui Postman collection:
https://www.postman.com/hsanaei/3x-ui/collection/q1l5l0u/3x-ui

Key differences from naive implementations:
- Uses `/panel/api/inbounds/...` (not `/api/inbounds/...`)
- Uses session cookies (not bearer tokens)
- `settings` parameter is JSON-stringified (double-encoded)
- Time values in milliseconds (not seconds)
- Sizes in bytes (not MB or GB)

## Implementation Files

- **`vpn_bot/xui_api.py`**: Complete API client implementation
- **`vpn_bot/handlers.py`**: Bot handlers that call the API
- **`vpn_bot/scheduler.py`**: Background worker for expiration

## Known Issues & Workarounds

### Nested Panel Paths
**Issue**: Panel hosted at `https://host:port/custom-path/`  
**Solution**: `urljoin()` used to properly construct URLs

### SSL Certificate Errors
**Issue**: Self-signed certificates cause verification failures  
**Solution**: Set `XUI_VERIFY_SSL=false` in environment (not recommended for production)

### Response Format Variations
**Issue**: Different panel versions wrap data under `obj`, `data`, or `result`  
**Solution**: `_extract_payload()` helper checks all possible keys

### Client ID vs UUID
**Issue**: Clients can have `id` or `uuid` field  
**Solution**: Code checks both fields when looking up clients

### Login Method Variations
**Issue**: Some 3x-ui panels expect JSON credentials, others expect form data  
**Solution**: Client tries JSON first, then falls back to form data automatically

### Cookie Name Variations
**Issue**: Different panel versions use different session cookie names  
**Solution**: Cookie-agnostic detection - any cookie set by the panel is accepted

### 403 vs 401 Authentication Errors
**Issue**: Some panels return 403 instead of 401 for expired sessions  
**Solution**: Both 401 and 403 trigger re-authentication

## New API Methods

The following new methods were added for compatibility with AlamorVPN_Bot patterns:

### List Inbounds
**Method**: `XUIClient.list_inbounds()`  
**API Endpoint**: `GET /panel/api/inbounds/list`  
**Description**: Returns a list of all configured inbounds

### Delete Client (Path-based)
**Method**: `XUIClient.delete_client_by_path(inbound_id, client_id)`  
**API Endpoint**: `POST /panel/api/inbounds/{inbound_id}/delClient/{client_id}`  
**Description**: Alternative deletion method used by some panel versions

### Get Client Traffic by ID
**Method**: `XUIClient.get_client_traffic_by_id(client_id)`  
**API Endpoint**: `GET /panel/api/inbounds/getClientTrafficsById/{client_id}`  
**Description**: Get traffic stats without knowing the inbound ID

### Get Client Info
**Method**: `XUIClient.get_client_info(client_id)`  
**Description**: Searches all inbounds for a client and returns full info with traffic

### Check Connection
**Method**: `XUIClient.check_connection()`  
**Description**: Validates panel connection and credentials

## Security Considerations

- Always use HTTPS in production
- Enable SSL verification (`XUI_VERIFY_SSL=true`)
- Store panel credentials in environment variables (not database)
- Use strong passwords for panel accounts
- Implement IP whitelisting on panel side
- Monitor API calls for suspicious patterns
- Rotate credentials regularly
