import json

from dotenv import dotenv_values
from together import Together

# Load API key from .env file
env_vars = dotenv_values('.env')
together_api_key = env_vars['TOGETHER_API_KEY']
client = Together(api_key=together_api_key)

system_prompt = """
    Você trabalha numa game house. Sua função é ajudar a criar mundos de fantasia onde os jogadores vão adorar jogar.
    Instruções:
    - gere apenas texto sem formatação.
    - use linguagem simples e clara, sem floreios.
    - Crie descrições com tamanho entre 3 e 5 frases, em português.
"""

world_prompt = """
    Gere um nome e uma descrição criativa para um mundo de fantasia único com um conceito interessante \
    sobre cidades construídas nas costas de bestas massivas.

    **Exemplo:**

    World Name: Khragoria

    World Description: Em Khragoria, as cidades não são construídas sobre terra firme, mas sim sobre as costas \
        de bestas massivas conhecidas como Titãs da Terra.

"""

model="meta-llama/Llama-3-70b-chat-hf"

world = []

#Creating world:
def create_world():
    global system_prompt, world_prompt, model
    output = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": world_prompt}
        ],
    )
    world_output = output.choices[0].message.content
    world_output = world_output.strip() # elimina espaços excedentes, tabs, parágrafos, etc.
    # Formatando o mundo num dicionário
    world = {
        "name": world_output.split('\n')[0].strip()
        .replace('World Name: ', ''),
        "description": '\n'.join(world_output.split('\n')[1:])
        .replace('World Description:', '').strip()
    }
    return world

world = create_world()
print(f"\n\nCriated world\n\n{world}\n\n")
# Creating 3 kingdoms as defined in the following prompt
kingdom_prompt = f"""
    Crie 3 reinos diferentes para um mundo de fantasia.
    Para cada reino, gere uma descrição baseada no mundo em que está inserido.
    Descreva líderes importantes, culturas, história do reino.
    Produza o conteúdo no seguinte formato, sem qualquer texto introdutório, com descrições em português:

    [Kingdom 1 Name: <NOME DO REINO>
    Kingdom 1 Description: <DESCRIÇÃO DO REINO>\n\n
    Kingdom 2 Name: <NOME DO REINO>
    Kingdom 2 Description: <DESCRIÇÃO DO REINO>\n\n
    Kingdom 3 Name: <NOME DO REINO>
    Kingdom 3 Description: <DESCRIÇÃO DO REINO>

"""

output = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": kingdom_prompt}
    ],
)
kingdoms_output = output.choices[0].message.content

print(f"\n\nkingdoms_output:\n\n{kingdoms_output}\n\n")

# Formatando os reinos como dicionário
kingdoms = {}
for output in kingdoms_output.split('\n\n'):
    kingdom_name = output.strip().split('\n')[0] \
        .split('Name: ')[1].strip()
    print(f'Created kingdom "{kingdom_name}" in {world["name"]}')
    kingdom_description = output.strip().split('\n')[1] \
        .split('Description: ')[1].strip()
    kingdom = {
        "name": kingdom_name,
        "description": kingdom_description,
        "world": world['name']
    }
    kingdoms[kingdom_name] = kingdom

# Adicionando os reinos ao mundo
world['kingdoms'] = kingdoms

print(f"\n\nworld:\n{world}")

"""  # shape of kingdoms:
    {	
        'name': 'Arkonix', 
        'description': 'Em Arkonix, ...', 
        'kingdoms': {
            'Eldrida': {
                'name': 'Eldrida', 
                'description': 'Eldrida é um reino de ...', 
                'world': 'Arkonix'
            }, 
            'Kraelion': {
                'name': 'Kraelion', 
                'description': 'Kraelion é ...', 
                'world': 'Arkonix'
            }, 
            'Calonia': {
                'name': 'Calonia', 
                'description': 'Calonia é ...', 
                'world': 'Arkonix'
            }
        }
    } 
"""

# Generating Towns
def get_town_prompt(world, kingdom):
    return f"""
        Crie 3 cidades diferentes para um reino e mundo de fantasia.
        Descreva a região em que está localizada, lugares importantes da cidade,
        e história interessante sobre ela.
        Produza o conteúdo no seguinte formato:
        Town 1 Name: <NOME DA CIDADE>
        Town 1 Description: <DESCRIÇÃO DA CIDADE>
        Town 2 Name: <NOME DA CIDADE>
        Descrição da Cidade 2: <DESCRIÇÃO DA CIDADE>
        Town 3 Name: <NOME DA CIDADE>
        Descrição da Cidade 3: <DESCRIÇÃO DA CIDADE>
        World name: {world['name']}
        World description: {world['description']}
        Kingdom name: {kingdom['name']}
        Kingdom description: {kingdom['description']}
    """

def create_towns(world, kingdom):
    print(f'\nCreating towns for kingdom: {kingdom["name"]}...')
    output = client.chat.completions.create(
      model="meta-llama/Llama-3-70b-chat-hf",
      messages=[
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": get_town_prompt(world, kingdom)}
      ],
    )
    towns_output = output.choices[0].message.content
    
    towns = {}
    for output in towns_output.split('\n\n'):
        town_name = output.strip().split('\n')[0]\
        .split('Name: ')[1].strip()
        print(f'- {town_name} created')
        
        town_description = output.strip().split('\n')[1]\
        .split('Description: ')[1].strip()
        
        town = {
          "name": town_name,
          "description": town_description,
          "world": world['name'],
          "kingdom": kingdom['name']
        }
        towns[town_name] = town
    kingdom["towns"] = towns

for kingdom in kingdoms.values():
    create_towns(world, kingdom)  

town = list(kingdom['towns'].values())[0]
print(f'\nTown 1 Description: \
{town["description"]}')


# Creating Non Playing Characters (NPCs)
def get_npc_prompt(world, kingdom, town): 
    return f"""
        Crie 3 personagens diferentes baseados no mundo, reino e cidade em que estão. \
        Descreva a aparência e profissão do personagem, bem como suas dores e desejos mais profundos. \
        Certifique-se de não repetir nomes nem descrições. \

        Produza o conteúdo no seguinte formato:
        
        Character 1 Name: <NOME DO PERSONAGEM>
        Character 1 Description: <DESCRIÇÃO DO PERSONAGEM>
        Character 2 Name: <NOME DO PERSONAGEM>
        Character 2 Description: <DESCRIÇÃO DO PERSONAGEM>
        Character 3 Name: <NOME DO PERSONAGEM>
        Character 3 Description: <DESCRIÇÃO DO PERSONAGEM>

        World Name: {world['name']}
        World Description: {world['description']}

        Kingdom Name: {kingdom['name']}
        Kingdom Description: {kingdom['description']}

        Town Name: {town['name']}
        Town Description: {town['description']}

        Character 1 Name:
    """

def create_npcs(world, kingdom, town):
    print(f'\nCreating characters for the town of: {town["name"]}...')
    output = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": get_npc_prompt(world, kingdom, town)}
        ],
        temperature=1 
    )

    npcs_output = output.choices[0].message.content
    npcs = {}
    for output in npcs_output.split('\n\n'):
        npc_name = output.strip().split('\n')[0]\
        .split('Name: ')[1].strip()
        print(f'- "{npc_name}" created')
        
        npc_description = output.strip().split('\n')[1\
        ].split('Description: ')[1].strip()
        
        npc = {
        "name": npc_name,
        "description": npc_description,
        "world": world['name'],
        "kingdom": kingdom['name'],
        "town": town['name']
        }
        npcs[npc_name] = npc
    town["npcs"] = npcs

for kingdom in kingdoms.values():
    for town in kingdom['towns'].values():
        create_npcs(world, kingdom, town)
  # For now we'll only generate npcs for one kingdom
  #  break


npc = list(town['npcs'].values())[0]

# Salvando o Jogo
def save_world(world, filename):
    with open(filename, 'w') as f:
        json.dump(world, f)

def load_world(filename):
    with open(filename, 'r') as f:
        return json.load(f)

save_world(world, './SeuMundo_L1.json')

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