import streamlit as st
import sys
import os
from supabase import create_client, Client

def get_supabase_client() -> Client:
    url = st.secrets["keys"]["SUPABASE_URL"]
    key = st.secrets["keys"]["SUPABASE_PUBLISHABLE_KEY"]
    
    # Suppress connection message printed by supabase library
    devnull = open(os.devnull, 'w')
    old_stdout = sys.stdout
    sys.stdout = devnull
    
    client = create_client(url, key)
    
    sys.stdout = old_stdout
    devnull.close()
    
    return client
