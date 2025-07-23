from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import google.generativeai as genai
from dotenv import load_dotenv
import os
import mysql.connector
from typing import Optional, List, Dict
from fastapi.staticfiles import StaticFiles
import json
from pydantic import BaseModel
import re

# Load environment variables
load_dotenv()
print("DEBUG - DB_USER:", os.getenv('DB_USER'))

# Configure Gemini API
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

# Load Gemini model
gemini_model = genai.GenerativeModel("models/gemini-1.5-pro-latest")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# MySQL Configuration
MYSQL_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'use_pure': True
}




# Load your metadata (could also be stored in MySQL)
with open('metadata.json', 'r', encoding='utf-8') as f:
    METADATA = json.load(f)

def call_gemini_chat(system_prompt: str, user_prompt: str) -> str:
    try:
        chat = gemini_model.start_chat()
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        response = chat.send_message(full_prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return ""

class ChatRequest(BaseModel):
    message: str
    language: str = "english"

def get_mysql_connection():
    """Create and return MySQL connection"""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

def extract_json_from_response(response_text: str) -> Optional[Dict]:
    """Try to extract JSON from LLM response text"""
    try:
        # First try to parse directly as JSON
        return json.loads(response_text)
    except json.JSONDecodeError:
        # If that fails, try to find JSON within the text
        try:
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return None
        except json.JSONDecodeError:
            return None

def classify_query(user_query: str, language: str = "english") -> str:
    """
    Classify the user query as either 'greeting' or 'analytical'
    Returns 'greeting' or 'analytical'
    """
    if language.lower() == "hindi":
        system_prompt = """उपयोगकर्ता के प्रश्न को वर्गीकृत करें। यदि यह एक सामान्य अभिवादन, परिचय या छोटी बातचीत है, तो 'greeting' लौटाएं।
अन्यथा, यदि यह एक विश्लेषणात्मक प्रश्न है जिसके लिए डेटाबेस से जानकारी की आवश्यकता है, तो 'analytical' लौटाएं।
केवल 'greeting' या 'analytical' शब्द वापस करें, कोई अतिरिक्त पाठ नहीं।"""
    else:
        system_prompt = """Classify the user query. If it's a general greeting, introduction, or small talk, return 'greeting'.
Otherwise, if it's an analytical question that requires information from the database, return 'analytical'.
Return only the word 'greeting' or 'analytical', no additional text."""

    try:
        response = call_gemini_chat(system_prompt, user_query)
        return response.lower().strip()
    except Exception as e:
        print(f"Error classifying query: {e}")
        return "analytical"  # Default to analytical if classification fails

def generate_greeting_response(user_query: str, language: str = "english") -> str:
    """
    Generate a friendly greeting response based on the user's message
    """
    if language.lower() == "hindi":
        system_prompt = """आप झारखंड सरकार की आधिकारिक सहायक हैं। उपयोगकर्ता के अभिवादन का उत्तर दें।
उत्तर मित्रवत, पेशेवर और सहायक होना चाहिए, लेकिन संक्षिप्त रखें।
यदि उपयोगकर्ता आपके बारे में पूछता है, तो बताएं कि आप झारखंड सरकार के लिए एक एआई सहायक हैं जो सरकारी सेवाओं और जानकारी के बारे में मदद करने के लिए हैं।
किसी भी सामान्य अभिवादन का उत्तर उचित और विनम्र तरीके से दें।"""
    else:
        system_prompt = """You are an official assistant for the Government of Jharkhand. Respond to the user's greeting.
The response should be friendly, professional and helpful, but keep it brief.
If the user asks about you, explain that you're an AI assistant for the Jharkhand government here to help with government services and information.
Respond to any general greetings appropriately and politely."""

    try:
        response = call_gemini_chat(system_prompt, user_query)
        return response
    except Exception as e:
        print(f"Error generating greeting response: {e}")
        if language.lower() == "hindi":
            return "नमस्ते! मैं झारखंड सरकार की सहायक हूँ। मैं आपकी कैसे मदद कर सकती हूँ?"
        else:
            return "Hello! I'm an assistant for the Jharkhand government. How can I help you today?"

def find_relevant_files(user_query: str, language: str = "english") -> List[int]:
    """
    Identify relevant file numbers based on user query using metadata
    Returns a list of file numbers
    """
    if language.lower() == "hindi":
        system_prompt = """आपको उपयोगकर्ता के प्रश्न के आधार पर सबसे प्रासंगिक फ़ाइल नंबरों की पहचान करनी है। 
केवल निम्नलिखित JSON प्रारूप में प्रासंगिक फ़ाइल नंबरों की सूची वापस करें:
{"relevant_files": [file_name1, file_name2]}"""
    else:
        system_prompt = """Identify the most relevant file numbers based on the user query.
Return only a JSON-formatted list of relevant file numbers in this format:
{"relevant_files": [file_name1, file_name2]}"""

    metadata_context = "\n".join(
        f"File {item['file_name']}: {item['description']}"
        for item in METADATA['data']
    )

    try:
        response_content = call_gemini_chat(
            system_prompt,
            f"Metadata:\n{metadata_context}\n\nUser Query: {user_query}"
        )
        result = extract_json_from_response(response_content)

        if result and 'relevant_files' in result:
            return result['relevant_files']

        print(f"Unexpected response format: {response_content}")
        return []

    except Exception as e:
        print(f"Error in finding relevant files: {e}")
        return []

def fetch_file_details(file_names: List[int]) -> List[Dict]:
    """
    Fetch file details from MySQL database
    Returns a list of dictionaries with file details
    """
    if not file_names:
        return []
    
    conn = get_mysql_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Convert file numbers to strings since all columns are text type
        file_names_str = [str(fn) for fn in file_names]
        placeholders = ', '.join(['%s'] * len(file_names_str))
        
        query = f"""
        SELECT file_name, page_number, heading, description, eng_description 
        FROM bipard_pdf 
        WHERE file_name IN ({placeholders})
        """
        
        cursor.execute(query, tuple(file_names_str))
        results = cursor.fetchall()
        
        # Convert back to proper types if needed
        for result in results:
            try:
                result['file_name'] = int(result['file_name'])
            except (ValueError, TypeError):
                pass
                
        return results
        
    except mysql.connector.Error as err:
        print(f"Error fetching file details: {err}")
        return []
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

def generate_analytical_response(user_query: str, file_details: List[Dict], language: str = "english") -> str:
    """
    Generate professional response based on retrieved file details
    """
    if not file_details:
        if language.lower() == "hindi":
            return "क्षमा करें, इस प्रश्न से संबंधित कोई जानकारी नहीं मिली। कृपया अपना प्रश्न स्पष्ट रूप से पूछें या अन्य शब्दों का प्रयोग करें।"
        else:
            return "Sorry, no information was found related to this query. Please rephrase your question or use different terms."

    context = "\n\n".join(
        f"File Number: {item['file_name']}\nFile Name: {item['file_name']}\nDescription: {item['description']}"
        for item in file_details
    )

    if language.lower() == "hindi":
        system_prompt = """आप झारखंड सरकार के लिए एक पेशेवर सहायक हैं। नीचे दी गई जानकारी के आधार पर उपयोगकर्ता के प्रश्न का उत्तर हिंदी में दीजिए।
उत्तर स्पष्ट, विस्तृत, सटीक और सरल भाषा में होना चाहिए ताकि आम नागरिक आसानी से समझ सकें।
उत्तर में सभी महत्वपूर्ण विवरण शामिल करें और आवश्यकता अनुसार सरकारी दस्तावेज़ों की भाषा भी उपयोग करें, लेकिन जटिल शब्दों की बजाय सरल और सहज शैली अपनाएं।"""
        prompt = f"प्रश्न:\n{user_query}\n\nसंदर्भ जानकारी:\n{context}\n\nकृपया उपरोक्त प्रश्न का उत्तर उपयोगकर्ता की समझ के अनुसार सरल, विस्तृत और सही जानकारी के साथ दीजिए।"
    else:
        system_prompt = """You are a professional assistant for the Government of Jharkhand. Based on the given information, respond to the user's query in English.
Make sure the response is clear, elaborate, accurate, and written in simple and understandable language so that common citizens can easily understand.
Use formal tone where necessary, but prioritize clarity and completeness of information over bureaucratic jargon."""
        prompt = f"Question:\n{user_query}\n\nContext:\n{context}\n\nPlease write a simple, detailed and informative response based on the context above."

    try:
        response_text = call_gemini_chat(system_prompt, prompt)
        return response_text
    except Exception as e:
        print(f"Error generating response: {e}")
        if language.lower() == "hindi":
            return "क्षमा करें, उत्तर जेनरेट करते समय एक त्रुटि हुई। कृपया बाद में पुनः प्रयास करें।"
        else:
            return "Sorry, an error occurred while generating the response. Please try again later."

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/chat")
async def chat(message: str = Form(...), language: str = Form("english")):
    # Step 1: Classify the query
    query_type = classify_query(message, language)
    print(f"Query classified as: {query_type}")
    
    if query_type == "greeting":
        # Generate a greeting response
        response = generate_greeting_response(message, language)
    else:
        # Handle analytical query
        # Step 2: Find relevant file numbers
        relevant_files = find_relevant_files(message, language)
        print(f"Relevant files identified: {relevant_files}")
        
        # Step 3: Fetch details for relevant files
        file_details = fetch_file_details(relevant_files)
        print(f"Fetched file details: {len(file_details)} items")
        
        # Step 4: Generate response based on retrieved files
        response = generate_analytical_response(message, file_details, language)
    
    return {"response": response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
