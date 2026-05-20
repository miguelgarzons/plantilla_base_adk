import requests
import json

# =============================================
# CONFIGURACIÓN
# =============================================
ACCESS_TOKEN = "1000.249fdfb1cdb1e8390ee9040efc436686.32395eae3b920c2e625a7283284ddd80"
# Cambia esta URL según tu región:
# .com (US) | .eu (Europa) | .com.au (Australia) | .in (India)
BASE_URL = "https://desk.zoho.com/api/v1"

HEADERS = {
    "Authorization": f"Zoho-oauthtoken {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# =============================================
# 1. OBTENER PORTALES (necesitas el orgId)
# =============================================
def get_portals():
    url = f"{BASE_URL}/portals"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()

# =============================================
# 2. LISTAR CATEGORÍAS DE LA BASE DE CONOCIMIENTO
# =============================================
def get_kb_categories(org_id):
    url = f"{BASE_URL}/kbCategories"
    params = {"limit": 50, "from": 1}
    headers = {**HEADERS, "orgId": org_id}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

# =============================================
# 3. LISTAR ARTÍCULOS DE LA BASE DE CONOCIMIENTO
# =============================================
def get_kb_articles(org_id, category_id=None):
    url = f"{BASE_URL}/kbArticles"
    params = {"limit": 50, "from": 1, "status": "published"}
    if category_id:
        params["categoryId"] = category_id
    headers = {**HEADERS, "orgId": org_id}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

# =============================================
# 4. OBTENER DETALLE DE UN ARTÍCULO
# =============================================
def get_article_detail(org_id, article_id):
    url = f"{BASE_URL}/kbArticles/{article_id}"
    headers = {**HEADERS, "orgId": org_id}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

# =============================================
# MAIN - RECORRE TODA LA BASE DE CONOCIMIENTO
# =============================================
def main():
    print("🔍 Obteniendo portales...")
    portals_data = get_portals()
    portals = portals_data.get("data", [])

    if not portals:
        print("No se encontraron portales.")
        return

    for portal in portals:
        org_id = str(portal.get("orgId"))
        portal_name = portal.get("portalName", "Sin nombre")
        print(f"\n📂 Portal: {portal_name} (orgId: {org_id})")

        # Obtener categorías
        print("\n  📁 Categorías:")
        categories_data = get_kb_categories(org_id)
        categories = categories_data.get("data", [])

        for cat in categories:
            cat_id = cat.get("id")
            cat_name = cat.get("name", "Sin nombre")
            print(f"    - [{cat_id}] {cat_name}")

            # Obtener artículos por categoría
            articles_data = get_kb_articles(org_id, category_id=cat_id)
            articles = articles_data.get("data", [])

            if articles:
                print(f"      📄 Artículos ({len(articles)}):")
                for article in articles:
                    art_id = article.get("id")
                    art_title = article.get("title", "Sin título")
                    art_status = article.get("status", "")
                    print(f"        • [{art_id}] {art_title} ({art_status})")
            else:
                print("      (Sin artículos publicados)")

    # Guardar toda la KB en un JSON
    print("\n💾 Guardando base de conocimiento en 'zoho_kb.json'...")
    all_data = {"portals": portals}
    with open("zoho_kb.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print("✅ Listo.")

if __name__ == "__main__":
    main()