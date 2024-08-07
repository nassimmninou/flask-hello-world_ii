import json
import os
import time
from flask import Flask, request, jsonify
import openai
from openai import OpenAI
import requests
from packaging import version


OPENAI_API_KEY = os.environ['OPENAI_API_KEY']
AIRTABLE_API_KEY = os.environ['AIRTABLE_API_KEY']

# Init OpenAI Client
client = OpenAI(api_key=OPENAI_API_KEY)
assistant_instructions = """
   Role and Behavior: The GPT should interact in Saudi Arabic and help users choose the perfect dietary supplement for their health needs. It should be fun, engaging, and concise, smoothly asking follow-up questions to gather more information.

   Tone and Style: Adopt a friendly and engaging tone, but ensure it is direct and concise. Use words like "ايش" instead of "شنو" and "مب" instead of "مش" to make the language more relatable to the Saudi audience.

   Follow-Up Questions: Encourage the GPT to ask follow-up questions to gather more information from users, ensuring interactions are smooth and responses are accurate and relevant. For example:

   "What are your health goals for the supplement?"
   "Do you have any allergies to specific ingredients?"
   "Are you currently following any specific diet?"
   Focus on Specific Topics: Keep the discussion focused on dietary supplements and general health, avoiding topics beyond this scope to ensure relevance and usefulness. For instance:

   "What supplements have you tried before, and how was your experience?"
   "Do you exercise regularly?"
   User Prompt Examples: Create example user prompts that evoke responses showcasing the GPT's unique behavior, ensuring they are directly targeted to the GPT's purpose. For example:

   "I need a supplement to boost my energy throughout the day."
   "What's the best supplement for strengthening the immune system?"
   "I have a vitamin D deficiency, what do you recommend?"
   "I want a supplement to improve my sleep."
   Consultation Reminder: When recommending a dietary supplement, remind the user that the GPT is not a doctor and that it is wise to consult one, ensuring users are aware of the limitations. For instance:

   This supplement is excellent for boosting energy, but it's best to consult your doctor before starting it."
   "This supplement helps strengthen the immune system, but make sure to consult your doctor first."
   Product Recommendations: When recommending products, provide links for easy purchase and a brief description of why the product is recommended, using global benchmarks and the latest innovations in the supplement industry as a basis. For example:

   "I recommend Omega-3 supplement from XYZ brand because it’s great for heart health. [Link to purchase]"
   "Vitamin C from ABC is known for strengthening the immune system. [Link to purchase]"
   Cultural Tailoring: Adapt the GPT's language and cultural references to fit the target audience, ensuring it resonates well with users. For instance:

   "This supplement is widely available in Saudi pharmacies."
   "This product is very popular among people in Saudi Arabia."
"""


# Add lead to Airtable
def create_lead(name, phone):
    url = "https://api.airtable.com/v0/appM1yx0NobvowCAg/Accelerator%20Leads"
    headers = {
        "Authorization": AIRTABLE_API_KEY,
        "Content-Type": "application/json"
    }
    data = {"records": [{"fields": {"Name": name, "Phone": phone}}]}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        print("Lead created successfully.")
        return response.json()
    else:
        print(f"Failed to create lead: {response.text}")


# Create or load assistant
def create_assistant(client):
    assistant_file_path = 'assistant.json'

    # If there is an assistant.json file already, then load that assistant
    if os.path.exists(assistant_file_path):
        with open(assistant_file_path, 'r') as file:
            assistant_data = json.load(file)
            assistant_id = assistant_data['assistant_id']
            print("Loaded existing assistant ID.")
    else:
        # If no assistant.json is present, create a new assistant using the below specifications

        # To change the knowledge document, modify the file name below to match your document
        # If you want to add multiple files, paste this function into ChatGPT and ask for it to add support for multiple files
        file = client.files.create(file=open("knowledge.docx", "rb"),
                                   purpose='assistants')

        assistant = client.beta.assistants.create(
            # Change prompting in prompts.py file
            instructions=assistant_instructions,
            model="gpt-4-1106-preview",
            tools=[

            ],
)
        # Create a new assistant.json file to load on future runs
        with open(assistant_file_path, 'w') as file:
            json.dump({'assistant_id': assistant.id}, file)
            print("Created a new assistant and saved the ID.")

        assistant_id = assistant.id

    return assistant_id

required_version = version.parse("1.1.1")
current_version = version.parse(openai.__version__)
OPENAI_API_KEY = os.environ['OPENAI_API_KEY']
if current_version < required_version:
  raise ValueError(
      f"Error: OpenAI version {openai.__version__} is less than the required version 1.1.1"
  )
else:
  print("OpenAI version is compatible.")

app = Flask(__name__)
client = OpenAI(api_key=OPENAI_API_KEY)

# Load assistant ID from file or create new one
assistant_id = create_assistant(client)
print("Assistant created with ID:", assistant_id)
# Create thread
@app.route('/start', methods=['GET'])
def start_conversation():
  thread = client.beta.threads.create()
  print("New conversation started with thread ID:", thread.id)
  return jsonify({"thread_id": thread.id})


# Start run
@app.route('/chat', methods=['POST'])
def chat():
  data = request.json
  thread_id = data.get('thread_id')
  user_input = data.get('message', '')
  if not thread_id:
    print("Error: Missing thread_id in /chat")
    return jsonify({"error": "Missing thread_id"}), 400
  print("Received message for thread ID:", thread_id, "Message:", user_input)

  # Start run and send run ID back to ManyChat
  client.beta.threads.messages.create(thread_id=thread_id,
                                      role="user",
                                      content=user_input)
  run = client.beta.threads.runs.create(thread_id=thread_id,
                                        assistant_id=assistant_id)
  print("Run started with ID:", run.id)
  return jsonify({"run_id": run.id})


# Check status of run
@app.route('/check', methods=['POST'])
def check_run_status():
  data = request.json
  thread_id = data.get('thread_id')
  run_id = data.get('run_id')
  if not thread_id or not run_id:
    print("Error: Missing thread_id or run_id in /check")
    return jsonify({"response": "error"})

  # Start timer ensuring no more than 9 seconds, ManyChat timeout is 10s
  start_time = time.time()
  while time.time() - start_time < 8:
    run_status = client.beta.threads.runs.retrieve(thread_id=thread_id,
                                                   run_id=run_id)
    print("Checking run status:", run_status.status)

    if run_status.status == 'completed':
      messages = client.beta.threads.messages.list(thread_id=thread_id)
      message_content = messages.data[0].content[0].text
      # Remove annotations
      annotations = message_content.annotations
      for annotation in annotations:
        message_content.value = message_content.value.replace(
            annotation.text, '')
      print("Run completed, returning response")
      return jsonify({
          "response": message_content.value,
          "status": "completed"
      })

    if run_status.status == 'requires_action':
      print("Action in progress...")
      # Handle the function call
      for tool_call in run_status.required_action.submit_tool_outputs.tool_calls:
        if tool_call.function.name == "create_lead":
          # Process lead creation
          arguments = json.loads(tool_call.function.arguments)
          output = create_lead(arguments["name"], arguments["phone"])
          client.beta.threads.runs.submit_tool_outputs(thread_id=thread_id,
                                                       run_id=run_id,
                                                       tool_outputs=[{
                                                           "tool_call_id":
                                                           tool_call.id,
                                                           "output":
                                                           json.dumps(output)
                                                       }])
    time.sleep(1)

  print("Run timed out")
  return jsonify({"response": "timeout"})


if __name__ == '__main__':
  app.run(host='0.0.0.0', port=8080)
