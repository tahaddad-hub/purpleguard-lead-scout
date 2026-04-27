import streamlit as st
from supabase import create_client, Client

def get_supabase_client() -> Client:
    url = st.secrets["keys"]["SUPABASE_URL"]
    key = st.secrets["keys"]["SUPABASE_PUBLISHABLE_KEY"]
    st.write("Connecting to: " + url[:30] + "...")
    return create_client(url, key)
