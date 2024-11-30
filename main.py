import gradio as gr
import base64
import json

from PIL import Image
from io import BytesIO
from dotenv import dotenv_values
from together import Together

# Salvando o Jogo
def save_world(world, filename):
    with open(filename, 'w') as f:
        json.dump(world, f)

def load_world(filename):
    with open(filename, 'r') as f:
        return json.load(f)


world = load_world('./SeuMundo_L1.json')
print(f"\n\nLoaded world {world['name']} \n\n")


# Esse bloco geral funciona
'''
demo = None  # added to allow restart
def start_game(main_loop, share=False):
    # added code to support restart
    global demo
    # If demo is already running, close it first
    if demo is not None:
        demo.close()

    demo = gr.ChatInterface(
        fn=main_loop,
        chatbot=gr.Chatbot(height=250, placeholder="Type 'start game' to begin"),
        textbox=gr.Textbox(placeholder="What do you do next?", container=False, scale=7),
        title="AI RPG",
        theme="soft",
        examples=["Look around", "Continue the story"],
        cache_examples=False
    )
    demo.launch(share=share, server_name="0.0.0.0")
def test_main_loop(message, history):
    # Return a tuple with the user message and the AI response
    return [message, 'Entered Action: ' + message]
# Uncomment the line below to start the game
start_game(test_main_loop)
'''

def get_game_state(inventory={}):
    world = load_world('./SeuMundo_L1.json')
    print(f"\n\nLoaded world {world['name']} \n\n")
    kingdom = world['kingdoms']['Eldrida']
    town = kingdom['towns']["Luminaria"]
    character = town['npcs']['Eira Shadowglow']
    start = world['start']

    game_state = {
        "world": world['description'],
        "kingdom": kingdom['description'],
        "town": town['description'],
        "character": character['description'],
        "start": start,
        "inventory": inventory
    }
    return game_state

def run_action(message, history, game_state):
    
    if(message == 'start game'):
        return game_state['start']
        
    system_prompt = """Você é o mestre do jogo de RPG. \
        Sua função é escrever o que acontece na próxima etapa do jogo.

        Instruções: \

        Você deve escrever de uma a três frases para responder. \
        Sempre responda na segunda pessoa do presente. \
        Ex. (Você olha para a direita e vê...)
    """
    
    world_info = f"""
World: {game_state['world']}
Kingdom: {game_state['kingdom']}
Town: {game_state['town']}
Your Character:  {game_state['character']}"""


    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": world_info}
    ]

    for action in history:
        messages.append({"role": "assistant", "content": action[0]})
        messages.append({"role": "user", "content": action[1]})
           
    messages.append({"role": "user", "content": message})
    client = Together(api_key=get_together_api_key())
    model_output = client.chat.completions.create(
        model="meta-llama/Llama-3-70b-chat-hf",
        messages=messages
    )
    
    result = model_output.choices[0].message.content
    return result

def start_game(main_loop, share=False):
    demo = gr.ChatInterface(
        main_loop,
        chatbot=gr.Chatbot(height=250, placeholder="Digite 'start game' para começar"),
        textbox=gr.Textbox(placeholder="O que você faz a seguir?", container=False, scale=7),
        title="AI RPG",
        # description="Ask Yes Man any question",
        theme="soft",
        examples=["Olhe em volta", "Continue a história"],
        cache_examples=False,
        retry_btn="Retry",
        undo_btn="Undo",
        clear_btn="Clear",
                           )
    demo.launch(share=share, server_name="0.0.0.0")












"""
def create_illustration(prompt):
    client = Together(api_key=together_api_key)

    response = client.images.generate(
        prompt=prompt,
        model="black-forest-labs/FLUX.1-schnell-Free",
        width=512,  # Smaller image width
        height=384, # Smaller image height
        steps=1,
        n=1,
        response_format="b64_json",
    )
    image_data = base64.b64decode(response.data[0].b64_json)
    
    # Save the image as a file
    file_path = "output_image.png"
    with open(file_path, "wb") as f:
        f.write(image_data)
    
    return file_path

def generate_state(prompt):
    
    global world_prompt

    client = Together(api_key=together_api_key)

    if not prompt:
        prompt = world_prompt

    output = client.chat.completions.create(
        model="meta-llama/Llama-3-70b-chat-hf",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    )
    
    world_output = output.choices[0].message.content
    image_path = create_illustration(world_output)  # Generate illustration based on world output
    
    return  image_path, world_output


# Gradio Interface
'''
gr.Interface(
    fn=generate_state,
    inputs=None,
    outputs=[gr.Image(label="Generated Illustration"), gr.Textbox(label="World Description") ],
    allow_flagging="never", # Hide the flag button
    clear_on_submit=False # Disable the Clear button
).launch()
'''

with gr.Blocks() as demo:
    with gr.Row():
        input_field = gr.Textbox(label="Input Text")
    with gr.Row():
        output_image = gr.Image(label="Generated Image")
    with gr.Row():
        output_text = gr.Textbox(label="World Description")

    btn = gr.Button("Generate")
    btn.click(fn=generate_state, inputs=input_field, outputs=[output_image, output_text])

demo.launch()
"""