import streamlit as st
import requests
import uuid
import os

# Server Connection Settings
API_URL = "https://al-aasar-telecom-egypt-agentic-rag-system.hf.space"

# Page Configuration
st.set_page_config(
    page_title="المساعد الذكي - Telecom Egypt",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    .main-title {
        text-align: center;
        color: #1E3A8A;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .sub-title {
        text-align: center;
        color: #6B7280;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# Main UI Title
st.markdown("<h1 class='main-title'>المساعد الذكي - Telecom Egypt</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-title'>نظام الذكاء الاصطناعي لتحليل المستندات والصور والإجابة على الاستفسارات</p>", unsafe_allow_html=True)

# Session and Welcome Message Initialization
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

WELCOME_MESSAGE = """
**مرحباً بك!**

أنا المساعد الذكي الخاص بـ **الشركة المصرية للاتصالات (Telecom Egypt)**. 
أنا هنا لتسهيل عملك ومساعدتك في الوصول إلى المعلومات بسرعة ودقة.

**كيف يمكنني مساعدتك اليوم؟**
* **اسألني** عن أي معلومات في قاعدة بياناتنا.
* **ارفع مستنداً** (PDF, Word, TXT) وسأقوم بقراءته وتلخيصه أو الإجابة على أسئلة محددة منه.
* **ارفع صورة** وسأقوم باستخراج النصوص منها وتحليلها.

تفضل بكتابة سؤالك بالأسفل، أو استخدم القائمة الجانبية لرفع الملفات.
"""

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": WELCOME_MESSAGE}]

# Sidebar
with st.sidebar:
    # Company logo
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/cc/Telecom_Egypt_logo.svg/512px-Telecom_Egypt_logo.svg.png", width=150)
    st.divider()
    
    st.header("إدارة الملفات")
    st.markdown("قم برفع ملفاتك الخاصة ليتمكن المساعد من قراءتها والإجابة بناءً عليها في هذه الجلسة.")
    
    uploaded_file = st.file_uploader("اختر ملفاً (PDF, DOCX, TXT, PNG, JPG)", type=["pdf", "docx", "txt", "png", "jpg", "jpeg"], label_visibility="collapsed")
    
    if st.button("رفع ومعالجة الملف", use_container_width=True):
        if uploaded_file is not None:
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            
            with st.spinner("جاري تحليل الملف... يرجى الانتظار"):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                data = {"session_id": st.session_state.session_id}
                
                try:
                    if ext in [".png", ".jpg", ".jpeg"]:
                        endpoint = f"{API_URL}/upload-image"
                    else:
                        endpoint = f"{API_URL}/upload-document"
                        
                    response = requests.post(endpoint, files=files, data=data)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("success"):
                            st.success(f"تمت قراءة '{uploaded_file.name}' بنجاح! يمكنك الآن سؤالي عنه.")
                        else:
                            st.error(f"خطأ: {result.get('message', 'حدث خطأ غير معروف')}")
                    else:
                        st.error(f"فشل الاتصال بالخادم. (Code: {response.status_code})")
                except Exception as e:
                    st.error("تأكد من تشغيل خادم FastAPI في الخلفية.")
        else:
            st.warning("يرجى اختيار ملف أولاً قبل الضغط على رفع.")
            
    st.divider()
    st.caption(f"معرف الجلسة: `{st.session_state.session_id[:8]}...`")
    
    if st.button("مسح المحادثة وبدء جلسة جديدة", type="secondary", use_container_width=True):
        st.session_state.messages = [{"role": "assistant", "content": WELCOME_MESSAGE}]
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# Main Chat Interface
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input
if prompt := st.chat_input("اكتب استفسارك هنا (مثال: ما هي الشروط والأحكام؟)..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Send request and receive response
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        with st.spinner("جاري معالجة البيانات واستخراج الإجابة..."):
            try:
                payload = {
                    "question": prompt,
                    "session_id": st.session_state.session_id
                }
                response = requests.post(f"{API_URL}/chat", json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    answer = result.get("answer", "لا أمتلك معلومات كافية للإجابة.")
                    
                    message_placeholder.markdown(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                else:
                    error_msg = "عذراً، حدث خطأ أثناء معالجة طلبك."
                    message_placeholder.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
                    
            except Exception as e:
                error_msg = "لا يمكن الاتصال بالخادم. يرجى التأكد من تشغيل الباك إند."
                message_placeholder.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})