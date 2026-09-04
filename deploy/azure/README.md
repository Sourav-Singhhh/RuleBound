# RuleBound Azure Deployment with Microsoft Entra ID Authentication

This directory provides an isolated, zero-dependency cloud deployment wrapper for the RuleBound engine on **Azure App Service** fronted by **Microsoft Entra ID Authentication (Easy Auth)**.

---

## 1. Architecture Overview

```
[ Client / Evaluator ]
          │
          │ 1. HTTPS POST /api/v1/solve + Authorization: Bearer <Entra_Token>
          ▼
┌───────────────────────────────────────────────────────────┐
│               AZURE APP SERVICE (EASY AUTH)               │
│  - Front-end reverse proxy automatically validates JWT:   │
│    • Issuer: https://login.microsoftonline.com/<tenant>/v2.0│
│    • Audience: api://rulebound-api                        │
│    • Signature & Expiry verified against Microsoft JWKS   │
│  - Unauthenticated requests rejected with HTTP 401        │
│  - Injects X-MS-CLIENT-PRINCIPAL claims upon success      │
└─────────────────────────────┬─────────────────────────────┘
                              │
                              │ 2. Forward to local WSGI (127.0.0.1:8000)
                              ▼
┌───────────────────────────────────────────────────────────┐
│              ISOLATED PYTHON SERVICE WRAPPER              │
│  - Path: deploy/azure/app.py (Pure standard library WSGI) │
│  - Receives JSON payload: {"room_id": "ROOM-02", ...}     │
│  - Invokes: generator -> constraints -> arbitration -> price│
│  - Produces schema-valid layout and quote JSON            │
└───────────────────────────────────────────────────────────┘
```

---

## 2. Deployment Instructions

### Prerequisites
- Active Azure Subscription
- Azure CLI (`az`) installed and authenticated (`az login`)
- Permission to register applications in Microsoft Entra ID

### Step 1: Create Microsoft Entra ID App Registration
```bash
# 1. Create App Registration
APP_ID=$(az ad app create --display-name "RuleBound-API" --query appId -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)

# 2. Expose API Scope
az ad app update --id $APP_ID --identifier-uris "api://$APP_ID"
```

### Step 2: Deploy Infrastructure via Bicep
```bash
# 1. Create Resource Group
az group create --name rg-rulebound-prod --location eastus

# 2. Deploy Azure App Service & Easy Auth
az deployment group create \
  --resource-group rg-rulebound-prod \
  --template-file deploy/azure/bicep/main.bicep \
  --parameters entraClientId=$APP_ID entraTenantId=$TENANT_ID
```

### Step 3: Deploy Application Code
```bash
# Deploy code via App Service Zip Deploy
az webapp deploy \
  --resource-group rg-rulebound-prod \
  --name $(az webapp list -g rg-rulebound-prod --query "[0].name" -o tsv) \
  --src-path . \
  --type zip
```

---

## 3. End-to-End Verification

### Test 1: Unauthenticated / Browser Access
Opening the endpoint in a browser or calling via API without an authorization header triggers Microsoft Entra ID protection:
```bash
curl -i -X POST https://<app-name>.azurewebsites.net/api/v1/solve \
  -H "Content-Type: application/json" \
  -d '{"room_id": "ROOM-02"}'
```
**Expected Response:**
Enforces Microsoft Entra authentication (HTTP 401 Unauthorized challenge or HTTP 302 redirect to Microsoft sign-in). Unauthenticated requests are blocked at the App Service gateway.

### Test 2: Authenticated Access via Entra ID Bearer Token
```bash
# Acquire Token (Requires Entra tenant access / client credentials)
TOKEN=$(az account get-access-token --resource "api://$APP_ID" --query accessToken -o tsv)

# Call Protected Endpoint
curl -i -X POST https://<app-name>.azurewebsites.net/api/v1/solve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"room_id": "ROOM-02"}'
```
**Expected Response:**
```json
{
  "room_id": "ROOM-02",
  "layout": {
    "room_id": "ROOM-02",
    "status": "valid",
    "placements": [...],
    "violations": []
  },
  "quote": {
    "quote_id": "QUOTE-ROOM-02",
    "room_id": "ROOM-02",
    "status": "priced",
    "currency": "INR",
    "summary": {
      "goods_after_adjustments_inr": 255436,
      "labour_inr": 5280,
      "freight_inr": 10217,
      "grand_total_inr": 270933
    }
  }
}
```
