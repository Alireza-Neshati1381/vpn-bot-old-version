# Manual Testing Guide

This guide helps you manually test the VPN bot's functionality.

## Prerequisites

1. Bot is running (`python main.py`)
2. You have set `TELEGRAM_BOT_TOKEN` and `BOT_ADMIN_PIN` environment variables
3. You have Telegram installed and can message the bot

## Test Scenarios

### 1. Initial Setup & Admin Registration

**Test**: First user becomes admin automatically

**Steps**:
1. Open Telegram and find your bot (search for bot username)
2. Send `/start`
3. Verify you see admin dashboard with buttons:
   - Add Server
   - List Servers
   - Add Plan
   - List Plans
   - Assign Roles
   - etc.

**Expected Result**: You are registered as ADMIN role

### 2. Language Selection

**Test**: User can switch between English and Persian

**Steps**:
1. Current implementation: Language set per user in database
2. Future: Add `/language` command or button
3. Check messages appear in correct language

**Expected Result**: UI updates to selected language

### 3. Server Management (Admin)

**Test**: Add and list servers

**Steps**:
1. Click "Add Server" button
2. Send: `Test Server,https://panel.example.com:8443,admin,adminpass`
3. Verify "Server saved" message
4. Click "List Servers"
5. Verify server appears in list
6. Click delete button if needed

**Expected Result**: Server is stored and can be managed

### 4. Inbound Management (Admin)

**Test**: Add inbound configuration

**Steps**:
1. Click "Add Inbound"
2. Send: `1,Main Inbound`  (where 1 is the inbound ID from your panel)
3. Verify "Inbound saved" message
4. Click "List Inbounds"
5. Verify inbound appears

**Expected Result**: Inbound is stored with friendly name

### 5. Prebuilt Plan Creation (Admin)

**Test**: Create a fixed-price package

**Steps**:
1. Click "Add Plan"
2. Choose "Prebuilt Package"
3. Send: `Basic Plan,1,1,US,50,30,1,10.00`
   - Name: Basic Plan
   - Server ID: 1
   - Inbound ID: 1
   - Country: US
   - Volume: 50 GB
   - Duration: 30 days
   - Max users: 1
   - Price: $10.00
4. Verify "Plan saved" message
5. Click "List Plans"
6. Verify plan appears with all details

**Expected Result**: Plan is created and visible

### 6. Per-GB Pricing Configuration (Admin)

**Test**: Configure dynamic pricing for a server

**Steps**:
1. Click "Pricing Settings"
2. Choose "Single Server" or "Apply to All"
3. If single server, select server ID
4. Send pricing config: `2.00,1,6,10,1.50`
   - Price per GB: $2.00
   - Min months: 1
   - Max months: 6
   - Extra month percent: 10%
   - Additional user price: $1.50
5. Verify "Pricing saved" message

**Expected Result**: Server pricing is configured

### 7. Role Assignment (Admin)

**Test**: Promote user to accountant

**Steps**:
1. Have another user send `/start` to the bot (they become USER)
2. As admin, click "Assign Roles"
3. Send: `@username ACCOUNTANT`
4. Verify "Role updated" message
5. Other user should now see accountant dashboard

**Expected Result**: User's role is changed

### 8. Bank Card Configuration (Admin)

**Test**: Set payment information

**Steps**:
1. Click "Set Bank Card"
2. Send: `1234-5678-9012-3456`
3. Verify "Bank card saved" message

**Expected Result**: Card number is stored for payment instructions

### 9. Customer Purchase Flow - Prebuilt Plan

**Test**: Customer orders a prebuilt package

**Steps**:
1. As regular user (not admin), send `/start`
2. Click "Buy Plan"
3. See list of available plans with prices
4. See bank card number for payment
5. Click "Buy #1" (or plan number)
6. Upload a photo (any image) as payment receipt
7. Verify "Receipt received" message

**Expected Result**: Order created with PENDING_REVIEW status

### 10. Customer Purchase Flow - Custom Plan

**Test**: Customer customizes a plan with dynamic pricing

**Steps**:
1. As regular user, click "Customize Plan"
2. Select server from list
3. Send volume: `100` (GB)
4. Send duration: `3` (months)
5. Send number of users: `2`
6. Review price breakdown showing:
   - Base volume cost
   - Extra months cost
   - Extra users cost
   - Total
7. Confirm order
8. Upload receipt photo

**Expected Result**: Custom order created with calculated price

### 11. Accountant Approval Flow

**Test**: Accountant reviews and approves receipt

**Steps**:
1. As accountant user, click "Pending Receipts"
2. See order with receipt image
3. See details: order #, username, plan name
4. Click "Approve #{id}"
5. Wait for provisioning (API call to panel)
6. Verify "Order approved" message
7. Check that customer receives:
   - "VPN configuration ready" message
   - Configuration link (vless://, vmess://, or trojan://)
   - Expiration date

**Expected Result**: 
- Order status changes to ACTIVE
- Customer receives config
- VPN is provisioned on panel

### 12. Accountant Rejection Flow

**Test**: Accountant rejects invalid receipt

**Steps**:
1. As accountant, click "Pending Receipts"
2. Find order to reject
3. Click "Reject #{id}"
4. Customer should receive rejection notification

**Expected Result**:
- Order status changes to REJECTED
- Customer notified to reupload

### 13. Order Status Check (Customer)

**Test**: Customer views their order history

**Steps**:
1. As customer, click "Order Status"
2. View list of orders with:
   - Order ID
   - Plan name
   - Status (WAITING_RECEIPT, PENDING_REVIEW, ACTIVE, REJECTED, EXPIRED)
   - Expiration date
   - Traffic used

**Expected Result**: All orders displayed with details

### 14. Expiration Worker

**Test**: Background worker removes expired VPNs

**Steps**:
1. Create an order with short expiration (modify duration_days in DB)
2. Approve the order
3. Wait for expiration
4. Background worker should:
   - Detect expired order
   - Call API to remove client from panel
   - Update order status to EXPIRED
   - Notify customer

**Expected Result**: VPN is deactivated automatically

### 15. Rate Limiting

**Test**: User cannot spam requests

**Steps**:
1. As any user, rapidly click buttons or send messages
2. After exceeding `RATE_LIMIT_PER_MIN` (default 20)
3. Should see "Too many requests" message

**Expected Result**: Rate limit enforced, request blocked

### 16. Security: Admin PIN

**Test**: Only authenticated admins can access features

**Expected**: 
- Future implementation: Require PIN entry before admin actions
- Current: Role-based access control already implemented

### 17. File Upload Security

**Test**: Only valid receipt images accepted

**Steps**:
1. Try uploading non-image file (PDF, EXE, etc.)
2. Should be rejected or handled safely
3. Try uploading very large file (>5MB if MAX_RECEIPT_SIZE_MB=5)

**Expected Result**: Invalid files rejected

### 18. Multi-Server Package

**Test**: Plan works across multiple servers

**Steps**:
1. Create plan with multiple servers in `plan_servers` table:
   ```sql
   INSERT INTO plan_servers (plan_id, server_id) VALUES (1, 1), (1, 2);
   ```
2. Customer purchases this plan
3. Admin can choose which server to provision on

**Expected Result**: Package associated with multiple servers

### 19. API Integration Test

**Test**: Verify actual API calls work

**Prerequisites**: Have a real 3x-ui panel running

**Steps**:
1. Configure server with real panel URL and credentials
2. Create order and approve
3. Monitor logs for API calls
4. Check panel to verify client was created
5. Get inbound details API call succeeds
6. Configuration link is generated correctly
7. Delete expired order
8. Check panel to verify client was removed

**Expected Result**: All API operations succeed

### 20. Error Handling

**Test**: Bot handles errors gracefully

**Scenarios to test**:
1. Invalid server credentials → Shows error to admin
2. Panel unreachable → Logs error, notifies admin
3. Invalid inbound ID → Returns error message
4. Malformed input → Validation error shown
5. Database error → Logged and handled

**Expected Result**: No crashes, errors are logged and reported

## Performance Testing

### Load Test
1. Create 100+ orders
2. Approve them in batch
3. Monitor memory usage
4. Check database performance

### Concurrent Users
1. Have multiple users interact simultaneously
2. Verify no race conditions
3. Check rate limiting works per-user

## Security Testing

### Input Validation
1. Try SQL injection in inputs: `'; DROP TABLE users; --`
2. Try XSS: `<script>alert('xss')</script>`
3. Try path traversal: `../../etc/passwd`
4. Try null bytes: `test\x00hidden`

**Expected**: All sanitized and blocked

### Authentication
1. Try accessing admin functions as regular user
2. Try manipulating callback data
3. Try forging messages

**Expected**: Access denied

## Troubleshooting During Tests

### Bot doesn't respond
- Check `python main.py` is running
- Verify `TELEGRAM_BOT_TOKEN` is set
- Check internet connectivity
- Review logs for errors

### API calls fail
- Verify panel URL is accessible
- Check credentials are correct
- Confirm `XUI_VERIFY_SSL` matches your setup
- Test panel manually with curl

### Database errors
- Check `vpn_bot.sqlite3` exists and is writable
- Run migrations if needed
- Check disk space

### Receipt uploads fail
- Verify `uploads/receipts/` directory exists
- Check directory permissions (writable)
- Verify `MAX_RECEIPT_SIZE_MB` setting

## Test Checklist

- [ ] Admin registration works
- [ ] Language selection (if implemented)
- [ ] Server CRUD operations
- [ ] Inbound management
- [ ] Prebuilt plan creation
- [ ] Per-GB pricing configuration
- [ ] Role assignment
- [ ] Bank card setting
- [ ] Customer prebuilt purchase flow
- [ ] Customer custom plan flow
- [ ] Accountant approval
- [ ] Accountant rejection
- [ ] Order status viewing
- [ ] Expiration worker
- [ ] Rate limiting
- [ ] File upload security
- [ ] Multi-server packages
- [ ] Real API integration
- [ ] Error handling
- [ ] Security validation

## Reporting Issues

When reporting issues, include:
1. Steps to reproduce
2. Expected behavior
3. Actual behavior
4. Relevant log output
5. Environment (Python version, OS, etc.)
6. Configuration (sanitized, no secrets)
