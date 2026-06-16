#!/usr/bin/env bash
# mcp-oauth-check.sh — Verifica que un servidor MCP con OAuth 2.1 está bien configurado
# Uso: ./mcp-oauth-check.sh https://tu-dominio.com/mcp

set -euo pipefail

MCP_URL="${1:?Uso: $0 https://dominio.com/mcp}"
BASE_URL="${MCP_URL%/mcp}"  # quita /mcp para obtener la base

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✅ $*${NC}"; }
fail() { echo -e "${RED}  ❌ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $*${NC}"; }
section() { echo -e "\n${YELLOW}═══ $* ═══${NC}"; }

# ─── 1. GET /mcp → debe devolver 401 con WWW-Authenticate correcto ───
section "1. GET $MCP_URL"
RESPONSE=$(curl -sv "$MCP_URL" 2>&1)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$MCP_URL")

if [ "$HTTP_CODE" = "401" ]; then
  ok "GET /mcp → 401 Unauthorized"
else
  fail "GET /mcp → $HTTP_CODE (esperado 401)"
fi

WWW_AUTH=$(curl -sI "$MCP_URL" | grep -i "WWW-Authenticate" || true)
if echo "$WWW_AUTH" | grep -q "oauth-protected-resource"; then
  ok "WWW-Authenticate contiene oauth-protected-resource"
  echo "     $WWW_AUTH"
elif echo "$WWW_AUTH" | grep -q "oauth-authorization-server"; then
  fail "WWW-Authenticate apunta a oauth-authorization-server (debe ser oauth-protected-resource)"
  echo "     $WWW_AUTH"
else
  fail "WWW-Authenticate ausente o incorrecto"
  echo "     $WWW_AUTH"
fi

# ─── 2. HEAD /mcp → debe aceptar HEAD ───
section "2. HEAD $MCP_URL"
HEAD_CODE=$(curl -s -o /dev/null -w "%{http_code}" --head "$MCP_URL")
if [ "$HEAD_CODE" = "401" ] || [ "$HEAD_CODE" = "200" ]; then
  ok "HEAD /mcp → $HEAD_CODE"
else
  fail "HEAD /mcp → $HEAD_CODE (esperado 200 o 401, no 405)"
fi

# ─── 3. /.well-known/oauth-protected-resource ───
section "3. GET $BASE_URL/.well-known/oauth-protected-resource"
PR_BODY=$(curl -s "$BASE_URL/.well-known/oauth-protected-resource")
PR_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/.well-known/oauth-protected-resource")

if [ "$PR_CODE" = "200" ]; then
  ok "oauth-protected-resource → 200"
  echo "$PR_BODY" | jq . 2>/dev/null || echo "$PR_BODY"
else
  fail "oauth-protected-resource → $PR_CODE"
fi

RESOURCE=$(echo "$PR_BODY" | jq -r '.resource' 2>/dev/null || true)
AUTH_SERVER=$(echo "$PR_BODY" | jq -r '.authorization_servers[0]' 2>/dev/null || true)

if [ "$RESOURCE" = "$MCP_URL" ]; then
  ok "resource coincide con $MCP_URL"
else
  fail "resource='$RESOURCE' no coincide con $MCP_URL"
fi

if [ -n "$AUTH_SERVER" ]; then
  ok "authorization_servers[0] = $AUTH_SERVER"
else
  fail "authorization_servers vacío o ausente"
fi

# ─── 4. /.well-known/oauth-authorization-server ───
section "4. GET $AUTH_SERVER/.well-known/oauth-authorization-server"
AS_BODY=$(curl -s "$AUTH_SERVER/.well-known/oauth-authorization-server")
AS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$AUTH_SERVER/.well-known/oauth-authorization-server")

if [ "$AS_CODE" = "200" ]; then
  ok "oauth-authorization-server → 200"
  echo "$AS_BODY" | jq . 2>/dev/null || echo "$AS_BODY"
else
  fail "oauth-authorization-server → $AS_CODE"
fi

ISSUER=$(echo "$AS_BODY" | jq -r '.issuer' 2>/dev/null || true)
AUTH_EP=$(echo "$AS_BODY" | jq -r '.authorization_endpoint' 2>/dev/null || true)
TOKEN_EP=$(echo "$AS_BODY" | jq -r '.token_endpoint' 2>/dev/null || true)
REG_EP=$(echo "$AS_BODY" | jq -r '.registration_endpoint' 2>/dev/null || true)
PKCE=$(echo "$AS_BODY" | jq -r '.code_challenge_methods_supported[]' 2>/dev/null || true)

[ "$ISSUER" = "$AUTH_SERVER" ] && ok "issuer coincide con $AUTH_SERVER" || fail "issuer='$ISSUER' no coincide con $AUTH_SERVER"
[ -n "$AUTH_EP" ]  && ok "authorization_endpoint: $AUTH_EP"  || fail "authorization_endpoint ausente"
[ -n "$TOKEN_EP" ] && ok "token_endpoint: $TOKEN_EP"          || fail "token_endpoint ausente"
[ -n "$REG_EP" ]   && ok "registration_endpoint: $REG_EP"     || fail "registration_endpoint ausente — DCR requerido"
echo "$PKCE" | grep -q "S256" && ok "PKCE S256 soportado" || fail "PKCE S256 no declarado"

# ─── 5. DCR — Dynamic Client Registration ───
section "5. POST $REG_EP (DCR)"
DCR_BODY=$(curl -s -X POST "$REG_EP" \
  -H "Content-Type: application/json" \
  -d '{
    "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
    "client_name": "mcp-oauth-check",
    "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"],
    "token_endpoint_auth_method": "none"
  }')
DCR_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$REG_EP" \
  -H "Content-Type: application/json" \
  -d '{
    "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
    "client_name": "mcp-oauth-check-2",
    "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"],
    "token_endpoint_auth_method": "none"
  }')

if [ "$DCR_CODE" = "201" ] || [ "$DCR_CODE" = "200" ]; then
  ok "DCR → $DCR_CODE"
  echo "$DCR_BODY" | jq . 2>/dev/null || echo "$DCR_BODY"
  CLIENT_ID=$(echo "$DCR_BODY" | jq -r '.client_id' 2>/dev/null || true)
  if echo "$CLIENT_ID" | grep -qE '^[0-9]+$'; then
    warn "client_id='$CLIENT_ID' es numérico — se recomienda UUID (puede causar problemas con algunos clientes)"
  else
    ok "client_id tiene formato string: $CLIENT_ID"
  fi
else
  fail "DCR → $DCR_CODE"
  echo "$DCR_BODY"
fi

section "Resumen"
echo "  MCP URL    : $MCP_URL"
echo "  Auth Server: $AUTH_SERVER"
echo "  /authorize : $AUTH_EP"
echo "  /token     : $TOKEN_EP"
echo "  /register  : $REG_EP"
echo ""
echo "  Callback Claude Desktop : https://claude.ai/api/mcp/auth_callback"
echo "  Callback Claude (futuro): https://claude.com/api/mcp/auth_callback"
