import streamlit as st
import anthropic
import requests
import openpyxl
import ast
import re
import pandas as pd
from datetime import datetime
from supabase_client import get_supabase_client

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Sales Growth Radar",
    page_icon="🛡️",
    layout="wide"
)

# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
if "user" not in st.session_state:
    st.session_state.user = None
if "user_profile" not in st.session_state:
    st.session_state.user_profile = None
if "detected_country" not in st.session_state:
    st.session_state.detected_country = None

# ─────────────────────────────────────────────
# LOGIN SCREEN
# ─────────────────────────────────────────────
def show_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🛡️ Sales Growth Radar")
        st.markdown("#### Please sign in to continue")
        st.divider()
        email = st.text_input("Email", placeholder="your@email.com", autocomplete="off")
        password = st.text_input("Password", type="password", placeholder="••••••••", autocomplete="new-password")
        login_button = st.button("Sign In", type="primary", use_container_width=True)

        if login_button:
            if not email or not password:
                st.error("Please enter your email and password.")
                return
            try:
                supabase = get_supabase_client()
                response = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
                if response.user:
                    profile = supabase.table("users")\
                        .select("*")\
                        .eq("id", response.user.id)\
                        .single()\
                        .execute()
                    if profile.data:
                        st.session_state.user = response.user
                        st.session_state.user_profile = profile.data
                        st.rerun()
                    else:
                        st.error("User profile not found. Please contact your administrator.")
                else:
                    st.error("Invalid email or password.")
            except Exception as e:
                st.error("Login failed. Please check your credentials.")

# ─────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────
def logout():
    try:
        supabase = get_supabase_client()
        supabase.auth.sign_out()
    except:
        pass
    st.session_state.user = None
    st.session_state.user_profile = None
    st.rerun()

# ─────────────────────────────────────────────
# LOAD COUNTRIES AND CITIES FROM SUPABASE
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_countries_and_cities():
    try:
        supabase = get_supabase_client()

        countries_response = supabase.table("countries")\
            .select("id, name")\
            .eq("is_active", True)\
            .order("name")\
            .execute()

        cities_response = supabase.table("cities")\
            .select("name, country_id")\
            .eq("is_active", True)\
            .order("name")\
            .execute()

        country_map = {c["id"]: c["name"] for c in countries_response.data}
        cities_dict = {}

        for city in cities_response.data:
            country_name = country_map.get(city["country_id"])
            if country_name:
                if country_name not in cities_dict:
                    cities_dict[country_name] = []
                cities_dict[country_name].append(city["name"])

        for country in cities_dict:
            cities_dict[country] = sorted(cities_dict[country])

        return cities_dict

    except Exception as e:
        st.error("Could not load countries from database: " + str(e))
        return {}

# ─────────────────────────────────────────────
# LOAD INDUSTRIES FROM SUPABASE
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_industries():
    try:
        supabase = get_supabase_client()
        response = supabase.table("industries")\
            .select("id, name")\
            .order("name")\
            .execute()
        return [i["name"] for i in response.data]
    except Exception as e:
        return []

# ─────────────────────────────────────────────
# LOAD VERTICALS FROM SUPABASE
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_verticals():
    try:
        supabase = get_supabase_client()
        response = supabase.table("verticals")\
            .select("id, name")\
            .order("name")\
            .execute()
        return [v["name"] for v in response.data]
    except Exception as e:
        return []

# ─────────────────────────────────────────────
# LOAD TENANT OWN DOMAINS FROM SUPABASE
# Admin manages this — zero hardcoding
# ─────────────────────────────────────────────
def load_own_domains(tenant_id):
    try:
        supabase = get_supabase_client()
        response = supabase.table("tenants")\
            .select("own_domains")\
            .eq("id", tenant_id)\
            .single()\
            .execute()
        if response.data and response.data.get("own_domains"):
            domains = [d.strip().lower() for d in response.data["own_domains"].split(",")]
            return [d for d in domains if d]
        return []
    except:
        return []

# ─────────────────────────────────────────────
# AUTO-DETECT USER COUNTRY
# ─────────────────────────────────────────────
def detect_user_country(available_countries):
    try:
        response = requests.get("https://ipapi.co/json/", timeout=3)
        data = response.json()
        detected = data.get("country_name", "").strip()

        if detected in available_countries:
            return detected

        detected_lower = detected.lower()
        for country in available_countries:
            if detected_lower == country.lower():
                return country

        for country in available_countries:
            if detected_lower in country.lower() or country.lower() in detected_lower:
                return country

    except:
        pass

    return "Egypt" if "Egypt" in available_countries else available_countries[0]

# ─────────────────────────────────────────────
# BUILD COUNTRY LIST — User country first, then alphabetical
# ─────────────────────────────────────────────
def build_country_list(cities_dict, user_country):
    all_countries = sorted(list(cities_dict.keys()))
    if user_country in all_countries:
        return [user_country] + [c for c in all_countries if c != user_country]
    return all_countries

# ─────────────────────────────────────────────
# WEB SEARCH — Returns snippets AND url map
# ─────────────────────────────────────────────
def search_web(query, serper_key):
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": serper_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": 10}
    response = requests.post(url, headers=headers, json=payload)
    results = response.json()

    snippets = []
    url_map  = {}

    if "answerBox" in results:
        snippets.append("Summary: " + results["answerBox"].get("snippet", ""))

    if "organic" in results:
        for r in results["organic"][:10]:
            link    = r.get("link", "")
            title   = r.get("title", "")
            snippet = r.get("snippet", "")

            snippets.append(
                "- " + title +
                ": " + snippet +
                " | URL: " + link
            )

            if link:
                try:
                    domain = link.split("//")[-1].split("/")[0].replace("www.", "")
                    if domain and domain not in url_map:
                        url_map[domain] = link
                except:
                    pass

    return "\n".join(snippets), url_map

# ─────────────────────────────────────────────
# EXTRACT DOMAIN FROM URL
# ─────────────────────────────────────────────
def extract_domain(url):
    if not url:
        return ""
    try:
        domain = url.split("//")[-1].split("/")[0].replace("www.", "").lower().strip()
        return domain
    except:
        return ""

# ─────────────────────────────────────────────
# KNOWN DIRECTORY DOMAINS — Not real company websites
# ─────────────────────────────────────────────
DIRECTORY_DOMAINS = [
    "clutch.co", "linkedin.com", "facebook.com", "twitter.com",
    "instagram.com", "yellowpages.com", "yelp.com", "bloomberg.com",
    "crunchbase.com", "zoominfo.com", "glassdoor.com", "indeed.com",
    "google.com", "wikipedia.org", "forbes.com", "reuters.com"
]

def is_directory_url(url):
    domain = extract_domain(url)
    return any(d in domain for d in DIRECTORY_DOMAINS)

# ─────────────────────────────────────────────
# PARSE AI RESPONSE
# ─────────────────────────────────────────────
def clean_and_parse(raw):
    raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
    raw = raw.encode("ascii", "ignore").decode("ascii")
    raw = re.sub(r",\s*\]", "]", raw)
    raw = re.sub(r",\s*\}", "}", raw)
    return ast.literal_eval(raw)

# ─────────────────────────────────────────────
# SAVE TO SUSPECTS WITH DEDUPLICATION
# ─────────────────────────────────────────────
def save_to_suspects(df, country, scope, user_profile):
    try:
        supabase = get_supabase_client()

        own_domains    = load_own_domains(user_profile.get("tenant_id"))
        saved_count    = 0
        skipped_count  = 0
        excluded_count = 0

        for _, row in df.iterrows():
            company_name = row.get("Company Name", "").strip()
            website      = row.get("Website", "").strip()
            domain       = extract_domain(website)

            # EXCLUSION 1 — Own company domains
            if domain and any(own in domain for own in own_domains):
                excluded_count += 1
                continue

            # EXCLUSION 2 — Directory URLs — strip URL, keep company
            if website and is_directory_url(website):
                website = ""
                domain  = ""

            # DEDUPLICATION 1 — By domain
            if domain:
                existing = supabase.table("suspects")\
                    .select("id")\
                    .ilike("website", f"%{domain}%")\
                    .execute()
                if existing.data and len(existing.data) > 0:
                    skipped_count += 1
                    continue

            # DEDUPLICATION 2 — By company name (fallback when no website)
            if not domain and company_name:
                existing = supabase.table("suspects")\
                    .select("id")\
                    .ilike("company_name", company_name)\
                    .execute()
                if existing.data and len(existing.data) > 0:
                    skipped_count += 1
                    continue

            # BUILD RECORD
            record = {
                "company_name": company_name,
                "city":         row.get("City", ""),
                "country":      country,
                "website":      website,
                "client_base":  row.get("Client Base", ""),
                "experience":   row.get("Experience", ""),
                "mission":      scope,
                "status":       "new",
                "is_active":    True,
                "phone":        "",
                "address":      "",
                "tenant_id":    user_profile.get("tenant_id"),
                "user_id":      user_profile.get("id"),
                "created_at":   datetime.utcnow().isoformat()
            }

            supabase.table("suspects").insert(record).execute()
            saved_count += 1

        return saved_count, skipped_count, excluded_count

    except Exception as e:
        st.error("Error saving to database: " + str(e))
        return 0, 0, 0

# ─────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────
def show_app():
    anthropic_key = st.secrets["keys"]["ANTHROPIC_API_KEY"]
    serper_key    = st.secrets["keys"]["SERPER_API_KEY"]

    # ── HEADER ──────────────────────────────
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("🛡️ Sales Growth Radar")
    with col2:
        profile = st.session_state.user_profile
        st.markdown(f"**{profile['name']}**")
        st.markdown(f"{profile['role'].replace('_', ' ').title()}")
        if st.button("Sign Out", use_container_width=True):
            logout()

    st.divider()

    # ── LOAD ALL DATA FROM DATABASE ─────────
    cities_dict = load_countries_and_cities()
    industries  = load_industries()
    verticals   = load_verticals()

    if not cities_dict:
        st.error("Could not load configuration from database. Please try again.")
        return

    # ── COUNTRY LIST — user country first ───
    if st.session_state.detected_country is None:
        st.session_state.detected_country = detect_user_country(sorted(list(cities_dict.keys())))
    user_country    = st.session_state.detected_country
    country_list    = build_country_list(cities_dict, user_country)
    country_options = ["All Countries"] + country_list

    # ── SIDEBAR ─────────────────────────────
    with st.sidebar:
        st.markdown("#### 🎯 Search Criteria")

        scope = st.selectbox(
            "Looking for",
            ["Partners", "Clients", "Mailing List"],
            index=0,
            key="scope"
        )

        industry_options = ["All Industries"] + industries if industries else ["All Industries"]
        industry = st.selectbox("Industry", industry_options, key="industry")

        vertical_options = ["All Verticals"] + verticals if verticals else ["All Verticals"]
        vertical = st.selectbox("Vertical", vertical_options, key="vertical")

        if "country" not in st.session_state:
            default_country_index = country_options.index(user_country) if user_country in country_options else 1
            st.session_state["country"] = country_options[default_country_index]
        country = st.selectbox("Country", country_options, key="country")

        if country == "All Countries":
            city = "All Countries"
            st.caption("Sorted by country then city.")
        else:
            city_options = ["All " + country] + cities_dict.get(country, [])
            if "city" in st.session_state and st.session_state["city"] not in city_options:
                st.session_state["city"] = city_options[0]
            city = st.selectbox("City", city_options, key="city")

        limit_on = st.checkbox("Limit results", value=False, key="limit_on")
        if limit_on:
            num_leads = st.number_input("Max results", min_value=1, value=10, step=5, key="num_leads")
        else:
            num_leads = 9999

        st.markdown("")
        search_button = st.button("🔍 Search", type="primary", use_container_width=True)

    # ── LOCATION LABELS ──────────────────────
    if country == "All Countries":
        location_display    = "All Countries"
        location_for_search = "worldwide"
        sort_by = "country"
    elif city.startswith("All "):
        location_display    = country
        location_for_search = country
        sort_by = "city"
    else:
        location_display    = f"{city}, {country}"
        location_for_search = f"{city}, {country}"
        sort_by = "none"

    # ── SEARCH CONTEXT HEADER ────────────────
    context_line = f"### 📍 {scope} — {location_display}"
    if industry != "All Industries":
        context_line += f" · {industry}"
    if vertical != "All Verticals":
        context_line += f" · {vertical}"
    st.markdown(context_line)

    # ── SEARCH EXECUTION ─────────────────────
    if search_button:
        client = anthropic.Anthropic(api_key=anthropic_key)

        industry_filter = f" in the {industry} industry" if industry != "All Industries" else ""
        vertical_filter = f" focused on {vertical}" if vertical != "All Verticals" else ""

        # Get tenant name for own-company exclusion in prompt
        tenant_name = ""
        try:
            supabase = get_supabase_client()
            tenant = supabase.table("tenants")\
                .select("name, own_domains")\
                .eq("id", profile.get("tenant_id"))\
                .single()\
                .execute()
            if tenant.data:
                tenant_name = tenant.data.get("name", "")
        except:
            pass

        # Build search queries
        with st.spinner(f"Searching for {scope.lower()} in {location_display}..."):
            if scope == "Partners":
                queries = [
                    f"IT system integrators cybersecurity {location_for_search} 2024",
                    f"managed service providers MSP {location_for_search} cybersecurity",
                    f"cybersecurity resellers partners {location_for_search} Cisco SonicWall",
                    f"IT solutions companies {location_for_search} network security",
                    f"list of IT companies {location_for_search}",
                    f"technology resellers distributors {location_for_search}"
                ]
            elif scope == "Clients":
                queries = [
                    f"companies {location_for_search}{industry_filter}{vertical_filter}",
                    f"enterprises {location_for_search}{industry_filter} digital transformation",
                    f"organizations {location_for_search}{vertical_filter} IT security",
                    f"businesses {location_for_search}{industry_filter} cybersecurity",
                    f"list of {industry_filter} companies {location_for_search}",
                    f"top companies {location_for_search}{vertical_filter}"
                ]
            else:
                queries = [
                    f"companies {location_for_search}{industry_filter}{vertical_filter}",
                    f"businesses {location_for_search}{industry_filter}",
                    f"organizations {location_for_search}{vertical_filter}",
                    f"IT companies {location_for_search}",
                    f"list of companies {location_for_search}{industry_filter}",
                    f"directory companies {location_for_search}{vertical_filter}"
                ]

            all_results      = ""
            combined_url_map = {}

            for query in queries:
                snippets, url_map = search_web(query, serper_key)
                all_results += f"\nSearch: {query}\nResults:\n{snippets}\n"
                combined_url_map.update(url_map)

        # AI ANALYSIS
        with st.spinner("Analyzing results..."):
            limit_instruction = f"up to {num_leads}" if num_leads < 9999 else "all"

            prompt = (
                f"You are a strict business development researcher. "
                f"We are looking for {scope.lower()} located in {location_for_search}. "
                f"Do NOT include companies from other locations. "
                f"If there are not enough companies found, return only what is available.\n"
            )

            if tenant_name:
                prompt += (
                    f"IMPORTANT: Do NOT include '{tenant_name}' or any of its brands "
                    f"in the results — this is our own company.\n"
                )

            if scope == "Partners":
                prompt += (
                    f"We need IT System Integrators, MSPs, IT Resellers, medium size 20-200 employees, "
                    f"who can resell Managed Cybersecurity Services and solutions "
                    f"from SonicWall, Barracuda, CrowdStrike, Cisco.\n"
                )
            elif scope == "Clients":
                prompt += f"We need potential client companies{industry_filter}{vertical_filter} who may need cybersecurity services.\n"
            else:
                prompt += f"We need a broad list of companies{industry_filter}{vertical_filter} for a mailing campaign.\n"

            prompt += (
                f"Based on these search results:\n{all_results}\n"
                f"Extract {limit_instruction} companies STRICTLY located in {location_for_search} "
                f"and return ONLY a Python list of lists with exactly these 6 fields:\n"
                f'[["Company Name", "City", "Client Base", "Known Vendors", "Experience", "Website"]]\n'
                f"Rules:\n"
                f"- Client Base: use exactly Enterprise, Medium, Small, or Mixed\n"
                f"- Known Vendors: list ALL vendors found, comma separated. Use empty string if none found.\n"
                f"- Experience: one sentence describing what the company does\n"
                f"- Website: copy the EXACT URL from the search result for this company. "
                f"Use empty string if no URL was found in the search results. NEVER guess or invent a URL.\n"
                f"Return ONLY the raw Python list. No markdown. No explanation. "
                f"If no companies found return empty list []."
            )

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}]
            )

            try:
                suspects = clean_and_parse(response.content[0].text)
            except Exception as e:
                st.error("Error parsing results: " + str(e))
                st.stop()

        if len(suspects) == 0:
            st.warning(f"No {scope.lower()} found in {location_display}. Try broadening your search criteria.")
        else:
            # ── BUILD DATAFRAME ──────────────────
            df = pd.DataFrame(suspects, columns=[
                "Company Name", "City",
                "Client Base", "Known Vendors", "Experience", "Website"
            ])

            # ── STEP 1: RESOLVE WEBSITE — prefer Serper URL, reject directories ──
            def resolve_website(row):
                claude_url = row.get("Website", "")
                if claude_url and is_directory_url(claude_url):
                    claude_url = ""
                domain = extract_domain(claude_url)
                if domain and domain in combined_url_map:
                    candidate = combined_url_map[domain]
                    if not is_directory_url(candidate):
                        return candidate
                return claude_url

            df["Website"] = df.apply(resolve_website, axis=1)

            # ── STEP 2: FILTER OWN COMPANY FROM DISPLAY ──
            own_domains = load_own_domains(st.session_state.user_profile.get("tenant_id"))
            if own_domains:
                df = df[~df["Website"].apply(
                    lambda w: any(d in extract_domain(w) for d in own_domains)
                )].reset_index(drop=True)

            # ── STEP 3: SORT ──
            if sort_by in ("country", "city"):
                df = df.sort_values(["City"]).reset_index(drop=True)

            # ── STEP 4: ADD SERIAL NUMBER ──
            df.insert(0, "#", range(1, len(df) + 1))

            st.success(f"✅ Found {len(df)} {scope.lower()} in {location_display}")

            # ── STEP 5: DISPLAY TABLE ──
            st.dataframe(
                df,
                use_container_width=True,
                height=600,
                hide_index=True,
                column_config={
                    "Website": st.column_config.LinkColumn(
                        "Website",
                        display_text="🔗 Visit"
                    ),
                    "#": st.column_config.NumberColumn("#", width="small"),
                    "Client Base": st.column_config.TextColumn("Client Base", width="small"),
                }
            )

            # ── STEP 6: SAVE TO SUSPECTS WITH DEDUPLICATION ──
            with st.spinner("Saving to database..."):
                saved, skipped, excluded = save_to_suspects(
                    df,
                    country if country != "All Countries" else location_display,
                    scope,
                    st.session_state.user_profile
                )

            # ── STEP 7: SAVE SUMMARY MESSAGE ──
            parts = []
            if saved    > 0: parts.append(f"💾 {saved} new suspects saved")
            if skipped  > 0: parts.append(f"⏭️ {skipped} already existed — skipped")
            if excluded > 0: parts.append(f"🚫 {excluded} excluded — own company")

            if saved > 0:
                st.info(" | ".join(parts))
            elif saved == 0 and skipped > 0:
                st.warning("⚠️ All results already exist in the database. No new suspects added.")
            elif saved == 0 and excluded > 0:
                st.warning("⚠️ All results were excluded. No new suspects added.")

            # ── STEP 8: EXCEL EXPORT ──
            export_df = df.copy()
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = scope
            headers = list(export_df.columns)
            for col, header in enumerate(headers, 1):
                ws.cell(row=1, column=col, value=header)
            today = datetime.now().strftime("%Y-%m-%d")
            for row_idx, row_data in enumerate(export_df.values.tolist(), 2):
                for col_idx, value in enumerate(row_data, 1):
                    ws.cell(row=row_idx, column=col_idx, value=str(value))

            safe_location = location_display.replace(", ", "_").replace(" ", "_")
            filename = f"SGR_{scope}_{safe_location}_{today}.xlsx"
            wb.save(filename)

            with open(filename, "rb") as f:
                st.download_button(
                    "📥 Download Excel", f, filename,
                    use_container_width=True
                )

    else:
        st.info("👈 Set your search criteria in the sidebar and click Search")

# ─────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────
if st.session_state.user is None:
    show_login()
else:
    show_app()
