import streamlit as st
import anthropic
import requests
import openpyxl
import ast
import re
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Purpleguard Partner Search Engine", page_icon="🛡️", layout="wide")
st.title("🛡️ Purpleguard Partner Search Engine")

anthropic_key = st.secrets["keys"]["ANTHROPIC_API_KEY"]
serper_key = st.secrets["keys"]["SERPER_API_KEY"]

with st.sidebar:
    st.header("🎯 Search Criteria")
    country = st.selectbox("Target Country", ["Egypt", "Saudi Arabia", "UAE", "Qatar", "Oman", "Kuwait", "Bahrain"])
    num_leads = st.number_input("Number of Leads", min_value=3, max_value=100, value=10)
    st.divider()
    search_button = st.button("🔍 Find Partners", type="primary", use_container_width=True)

def search_web(query):
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
            snippets.append("- " + r.get("title", "") + ": " + r.get("snippet", "") + " | URL: " + r.get("link", ""))
    return "\n".join(snippets)

def clean_and_parse(raw):
    raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
    raw = raw.encode("ascii", "ignore").decode("ascii")
    raw = re.sub(r",\s*\]", "]", raw)
    raw = re.sub(r",\s*\}", "}", raw)
    return ast.literal_eval(raw)

if search_button:
    client = anthropic.Anthropic(api_key=anthropic_key)

    with st.spinner("Searching the web for potential partners..."):
        queries = [
            "IT system integrators cybersecurity " + country + " 2024",
            "managed service providers MSP " + country + " cybersecurity",
            "cybersecurity resellers partners " + country + " Cisco SonicWall",
            "IT solutions companies " + country + " network security"
        ]
        all_results = ""
        for query in queries:
            results = search_web(query)
            all_results += "\nSearch: " + query + "\nResults:\n" + results + "\n"

    with st.spinner("Analyzing and qualifying leads..."):
        prompt = "You are a business development researcher for Purpleguard, a cybersecurity company offering Managed Cybersecurity Services, Active and Passive solutions, and vendor partnerships with SonicWall, Barracuda, CrowdStrike, Cisco. We need PARTNERS in " + country + " who can resell our services. Ideal partner: IT System Integrators, MSPs, IT Resellers, medium size 20-200 employees. Based on these search results:\n" + all_results + "\nExtract " + str(num_leads) + " potential partners and return ONLY a Python list of lists:\n[[\"Company Name\", \"Country\", \"What They Do\", \"Cybersecurity Practice Yes/No/Partial\", \"Managed Services Strong/Weak/None\", \"Known Vendors\", \"Has Sales Team Yes/No\", \"Client Base\", \"Website\", \"Fit Score High/Medium/Low\"]]\nReturn ONLY the raw list no markdown no explanation."

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

    st.success("Found " + str(len(leads)) + " potential partners in " + country + "!")

    headers = ["Company Name", "Country", "What They Do", "Cybersecurity Practice", "Managed Services", "Known Vendors", "Has Sales Team", "Client Base", "Website", "Fit Score"]
    df = pd.DataFrame(leads, columns=headers)
    st.dataframe(df, use_container_width=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leads"
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    today = datetime.now().strftime("%Y-%m-%d")
    for row, lead in enumerate(leads, 2):
        for col, value in enumerate(lead, 1):
            ws.cell(row=row, column=col, value=value)
        ws.cell(row=row, column=11, value=today)
    wb.save("purpleguard_leads.xlsx")

    with open("purpleguard_leads.xlsx", "rb") as f:
        st.download_button("📥 Download Excel", f, "purpleguard_leads.xlsx", use_container_width=True)

else:
    st.info("👈 Select your target country and click Find Partners!")
