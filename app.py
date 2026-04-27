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

# ─────────────────────────────────────────────
# LOGIN SCREEN
# ─────────────────────────────────────────────
def show_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🛡️ Sales Growth Radar")
        st.markdown("#### Please sign in to continue")
        st.divider()

        email = st.text_input("Email", placeholder="your@email.com")
        password = st.text_input("Password", type="password", placeholder="••••••••")
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
                supabase_url = st.secrets["keys"]["SUPABASE_URL"]
                st.error("Login failed: " + str(e) + " | URL: " + supabase_url)

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
# LOAD CITIES FROM SUPABASE
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_cities():
    try:
        supabase = get_supabase_client()

        countries_response = supabase.table("countries")\
            .select("id, name")\
            .order("name")\
            .execute()

        cities_response = supabase.table("cities")\
            .select("name, country_id")\
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
            cities_dict[country] = ["All " + country] + sorted(cities_dict[country])

        return cities_dict

    except Exception as e:
        st.error("Could not load cities from database: " + str(e))
        return {}

# ─────────────────────────────────────────────
# AUTO-DETECT USER COUNTRY
# ─────────────────────────────────────────────
def get_user_country():
    try:
        response = requests.get("https://ipapi.co/json/", timeout=3)
        data = response.json()
        detected = data.get("country_name", "Egypt")
        country_map = {
            "Egypt": "Egypt",
            "Saudi Arabia": "Saudi Arabia",
            "United Arab Emirates": "UAE",
            "Qatar": "Qatar",
            "Oman": "Oman",
            "Kuwait": "Kuwait",
            "Bahrain": "Bahrain"
        }
        return country_map.get(detected, "Egypt")
    except:
        return "Egypt"

# ─────────────────────────────────────────────
# WEB SEARCH
# ─────────────────────────────────────────────
def search_web(query, serper_key):
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": serper_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": 5}
    response = requests.post(url, headers=headers, json=payload)
    results = response.json()
    snippets = []
    if "answerBox" in results:
        snippets.append("Summary: " + results["answerBox"].get("snippet", ""))
    if "organic" in results:
        for r in results["organic"][:5]:
            snippets.append(
                "- " + r.get("title", "") +
                ": " + r.get("snippet", "") +
                " | URL: " + r.get("link", "")
            )
    return "\n".join(snippets)

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
# MAIN APP
# ─────────────────────────────────────────────
def show_app():
    anthropic_key = st.secrets["keys"]["ANTHROPIC_API_KEY"]
    serper_key = st.secrets["keys"]["SERPER_API_KEY"]

    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("🛡️ Sales Growth Radar")
    with col2:
        profile = st.session_state.user_profile
        st.markdown(f"**{profile['name']}** · {profile['role'].replace('_', ' ').title()}")
        if st.button("Sign Out", use_container_width=True):
            logout()

    st.divider()

    cities = load_cities()

    if not cities:
        st.error("Could not load configuration from database. Please try again.")
        return

    default_country = get_user_country()
    country_list = sorted(list(cities.keys()))
    default_index = country_list.index(default_country) if default_country in country_list else 0

    with st.sidebar:
        st.header("🎯 Search Criteria")
        country = st.selectbox("Target Country", country_list, index=default_index)
        city_list = cities.get(country, ["All " + country])
        city = st.selectbox("Target City", city_list)
        num_leads = st.number_input("Number of Leads", min_value=3, max_value=100, value=10)
        st.divider()
        search_button = st.button("🔍 Find Partners", type="primary", use_container_width=True)

    location = city + ", " + country if not city.startswith("All") else country

    if search_button:
        client = anthropic.Anthropic(api_key=anthropic_key)

        with st.spinner("Searching the web for potential partners in " + location + "..."):
            queries = [
                "IT system integrators cybersecurity " + location + " 2024",
                "managed service providers MSP " + location + " cybersecurity",
                "cybersecurity resellers partners " + location + " Cisco SonicWall",
                "IT solutions companies " + location + " network security"
            ]
            all_results = ""
            for query in queries:
                results = search_web(query, serper_key)
                all_results += "\nSearch: " + query + "\nResults:\n" + results + "\n"

        with st.spinner("Analyzing and qualifying leads..."):
            prompt = (
                "You are a strict business development researcher for Purpleguard, a cybersecurity company. "
                "We need PARTNERS specifically located in " + location + " only. "
                "Do NOT include companies from other cities or countries. "
                "If there are not enough companies found, return only what is available. "
                "We need IT System Integrators, MSPs, IT Resellers, medium size 20-200 employees, "
                "who can resell Managed Cybersecurity Services and solutions from SonicWall, Barracuda, CrowdStrike, Cisco. "
                "Based on these search results:\n" + all_results +
                "\nExtract up to " + str(num_leads) + " potential partners STRICTLY located in " + location +
                " and return ONLY a Python list of lists:\n"
                "[[\"Company Name\", \"Country\", \"City\", \"What They Do\", "
                "\"Cybersecurity Practice Yes/No/Partial\", \"Managed Services Strong/Weak/None\", "
                "\"Known Vendors\", \"Has Sales Team Yes/No\", \"Client Base\", \"Website\", "
                "\"Fit Score High/Medium/Low\"]]\n"
                "Return ONLY the raw list no markdown no explanation. "
                "If no companies found return empty list []."
            )

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}]
            )

            try:
                leads = clean_and_parse(response.content[0].text)
            except Exception as e:
                st.error("Error parsing results: " + str(e))
                st.stop()

        if len(leads) == 0:
            st.warning("No partners found specifically in " + location + ". Try a broader area or different city.")
        else:
            st.success("Found " + str(len(leads)) + " potential partners in " + location + "!")

            headers = [
                "Company Name", "Country", "City", "What They Do",
                "Cybersecurity Practice", "Managed Services", "Known Vendors",
                "Has Sales Team", "Client Base", "Website", "Fit Score"
            ]
            df = pd.DataFrame(leads, columns=headers)
            st.dataframe(df, use_container_width=True, height=600)

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Leads"
            for col, header in enumerate(headers, 1):
                ws.cell(row=1, column=col, value=header)
            today = datetime.now().strftime("%Y-%m-%d")
            for row, lead in enumerate(leads, 2):
                for col, value in enumerate(lead, 1):
                    ws.cell(row=row, column=col, value=value)
                ws.cell(row=row, column=12, value=today)
            wb.save("purpleguard_leads.xlsx")

            with open("purpleguard_leads.xlsx", "rb") as f:
                st.download_button(
                    "📥 Download Excel", f,
                    "purpleguard_leads.xlsx",
                    use_container_width=True
                )

    else:
        st.info("👈 Select your target country and city, then click Find Partners!")

# ─────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────
if st.session_state.user is None:
    show_login()
else:
    show_app()
