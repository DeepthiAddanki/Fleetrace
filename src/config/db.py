from supabase import create_client


# db = create_client("sb_publishable_oGYpocVYH4rXoGmkyJbWFA_XJykZml9")
SUPABASE_URL = "https://cvtfwfsdjwfpxrcvmkjk.supabase.co"
SUPABASE_KEY = "sb_publishable_oGYpocVYH4rXoGmkyJbWFA_XJykZml9"


db = create_client(SUPABASE_URL,SUPABASE_KEY)