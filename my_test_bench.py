"""
def generate_state(prompt):
    
    global world_prompt, client, model

    if not prompt:
        prompt = world_prompt

    output = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    )
    
    world_output = output.choices[0].message.content
    image_path = create_illustration(world_output)  # Generate illustration based on world output
    
    return  image_path, world_output


# Gradio Interface

with gr.Blocks() as demo:
    with gr.Row():
        output_image = gr.Image(label="Generated Image")
    with gr.Row():
        output_text = gr.Textbox(label="World Description")
    with gr.Row():
        input_field = gr.Textbox(label="Input Text")

    btn = gr.Button("Entre com próxima ação")
    btn.click(fn=generate_state, inputs=input_field, outputs=[output_image, output_text])

demo.launch()
"""

import datetime
import json

test_game_state = {
    "world": "world['description']",
    "kingdom": "initial_kingdom['description']",
    "town": "initial_town['description']",
    "character": "initial_character['description']",
    "start": "world['description']",
    "inventory": "initial_inventory",
    "output_image" : "default_image_file_path"
}

def save_json(world, filename):
    with open(filename, 'w') as f:
        json.dump(world, f)

def load_json(filename):
    with open(filename, 'r') as f:
        return json.load(f)


def save_game(file_path, game_state):
    try:
        if file_path is None:
            return "Please select a file to save the game state."
        timed_file_path = f"{file_path}_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
        save_json(game_state, timed_file_path)
        return f"Game state saved to {file_path} successfully!"
    except Exception as e:
        return f"Failed to save game: {e}"


def retrieve_game(file_path):
    try:
        if file_path is None:
            return [], "Please select a file to retrieve the game state.", default_image_file_path, initial_game_state
        game_state = load_json(file_path.name)
        history = [{"role": "system", "content": system_prompt}]
        output = "Game state retrieved successfully! You can continue your adventure."
        return history, output, default_image_file_path, game_state
    except Exception as e:
        return [], f"Failed to retrieve game: {e}", default_image_file_path, initial_game_state



