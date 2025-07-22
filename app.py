from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import ollama
import mysql.connector
from typing import Optional, List, Dict
from fastapi.staticfiles import StaticFiles
import json
from pydantic import BaseModel
import re

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# MySQL Configuration
MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'ranchi'
}

# Load your metadata (could also be stored in MySQL)
with open('metadata.json', 'r', encoding='utf-8') as f:
    METADATA = json.load(f)

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

def find_relevant_files(user_query: str, language: str = "english") -> List[int]:
    """
    Identify relevant file numbers based on user query using metadata
    Returns a list of file numbers
    """
    if language.lower() == "hindi":
        system_prompt = """आपको उपयोगकर्ता के प्रश्न के आधार पर सबसे प्रासंगिक फ़ाइल नंबरों की पहचान करनी है। 
        केवल निम्नलिखित JSON प्रारूप में प्रासंगिक फ़ाइल नंबरों की सूची वापस करें:
        {"relevant_files": [file_number1, file_number2]}"""
    else:
        system_prompt = """Identify the most relevant file numbers based on the user query. 
        Return only a JSON-formatted list of relevant file numbers in this format:
        {"relevant_files": [file_number1, file_number2]}"""
    
    # Prepare metadata context
    metadata_context = "\n".join(
        f"File {item['file_number']}: {item['description']}" 
        for item in METADATA['data']
    )
    
    try:
        response = ollama.chat(
            model='llama3',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f"Metadata:\n{metadata_context}\n\nUser Query: {user_query}"}
            ],
            format='json'  # Request JSON format response
        )
        
        # Extract JSON from response
        response_content = response['message']['content']
        result = extract_json_from_response(response_content)
        
        if result and 'relevant_files' in result:
            return result['relevant_files']
        
        print(f"Unexpected response format: {response_content}")
        return []
    
    except Exception as e:
        print(f"Error in finding relevant files: {e}")
        return []

def fetch_file_details(file_numbers: List[int]) -> List[Dict]:
    """
    Fetch file details from MySQL database
    Returns a list of dictionaries with file details
    """
    if not file_numbers:
        return []
    
    conn = get_mysql_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Convert file numbers to strings since all columns are text type
        file_numbers_str = [str(fn) for fn in file_numbers]
        placeholders = ', '.join(['%s'] * len(file_numbers_str))
        
        query = f"""
        SELECT file_number, file_name, description 
        FROM data 
        WHERE file_number IN ({placeholders})
        """
        
        cursor.execute(query, tuple(file_numbers_str))
        results = cursor.fetchall()
        
        # Convert back to proper types if needed
        for result in results:
            try:
                result['file_number'] = int(result['file_number'])
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

def generate_response(user_query: str, file_details: List[Dict], language: str = "english") -> str:
    """
    Generate professional response based on retrieved file details
    """
    if not file_details:
        if language.lower() == "hindi":
            return "क्षमा करें, इस प्रश्न से संबंधित कोई जानकारी नहीं मिली। कृपया अपना प्रश्न स्पष्ट रूप से पूछें या अन्य शब्दों का प्रयोग करें।"
        else:
            return "Sorry, no information was found related to this query. Please rephrase your question or use different terms."
    
    # Prepare context for LLM
    context = "\n\n".join(
        f"File Number: {item['file_number']}\nFile Name: {item['file_name']}\nDescription: {item['description']}"
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
        response = ollama.chat(
            model='llama3',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt}
            ]
        )
        return response['message']['content']
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
    # Step 1: Find relevant file numbers
    relevant_files = find_relevant_files(message, language)
    print(f"Relevant files identified: {relevant_files}")
    
    # Step 2: Fetch details for relevant files
    file_details = fetch_file_details(relevant_files)
    print(f"Fetched file details: {len(file_details)} items")
    
    # Step 3: Generate response based on retrieved files
    response = generate_response(message, file_details, language)
    
    return {"response": response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
