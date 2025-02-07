import base64
import os
import re
import requests
import streamlit as st

from api_utils import send_request_to_groq_api               
from bs4 import BeautifulSoup
from ui_utils import get_api_key, regenerate_json_files_and_zip, update_discussion_and_whiteboard


def agent_button_callback(agent_index):
    # Callback function to handle state update and logic execution
    def callback():
        st.session_state['selected_agent_index'] = agent_index
        agent = st.session_state.agents[agent_index]

        agent_name = agent['config']['name'] if 'config' in agent and 'name' in agent['config'] else ''
        st.session_state['form_agent_name'] = agent_name
        st.session_state['form_agent_description'] = agent['description'] if 'description' in agent else ''
        # Directly call process_agent_interaction here if appropriate
        process_agent_interaction(agent_index)
    return callback


def construct_request(agent_name, description, user_request, user_input, rephrased_request, reference_url):
    request = f"Act as the {agent_name} who {description}."
    if user_request:
        request += f" Original request was: {user_request}."
    if rephrased_request:
        request += f" You are helping a team work on satisfying {rephrased_request}."
    if user_input:
        request += f" Additional input: {user_input}."
    if reference_url:
        try:
            response = requests.get(reference_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            url_content = soup.get_text()
            request += f" Reference URL content: {url_content}."
        except requests.exceptions.RequestException as e:
            print(f"Error occurred while retrieving content from {reference_url}: {e}")
    if st.session_state.discussion:
        request += f" The discussion so far has been {st.session_state.discussion[-50000:]}."
    return request


def delete_agent(index):
    if 0 <= index < len(st.session_state.agents):
        expert_name = st.session_state.agents[index]["expert_name"]
        del st.session_state.agents[index]
        
        # Get the full path to the JSON file
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "agents"))
        json_file = os.path.join(agents_dir, f"{expert_name}.json")
        
        # Delete the corresponding JSON file
        if os.path.exists(json_file):
            os.remove(json_file)
            print(f"JSON file deleted: {json_file}")
        else:
            print(f"JSON file not found: {json_file}")
        
        st.experimental_rerun()


def display_agents():
    if "agents" in st.session_state and st.session_state.agents:
        st.sidebar.title("Your Agents")
        st.sidebar.subheader("Click to interact")
        display_agent_buttons(st.session_state.agents)
        if st.session_state.get('show_edit'):
            edit_index = st.session_state.get('edit_agent_index')
            if edit_index is not None and 0 <= edit_index < len(st.session_state.agents):
                agent = st.session_state.agents[edit_index]
                display_agent_edit_form(agent, edit_index)
            else:
                st.sidebar.warning("Invalid agent selected for editing.")
    else:
        st.sidebar.warning("No agents have yet been created. Please enter a new request.")


def display_agent_buttons(agents):
    for index, agent in enumerate(agents):
        agent_name = agent["config"]["name"] if agent["config"].get("name") else f"Unnamed Agent {index + 1}"
        col1, col2 = st.sidebar.columns([1, 4])
        with col1:
            gear_icon = "⚙️"  # Unicode character for gear icon
            if st.button(gear_icon, key=f"gear_{index}"):
                st.session_state['edit_agent_index'] = index
                st.session_state['show_edit'] = True
        with col2:
            if "next_agent" in st.session_state and st.session_state.next_agent == agent_name:
                button_style = """
                <style>
                div[data-testid*="stButton"] > button[kind="secondary"] {
                    background-color: green !important;
                    color: white !important;
                }
                </style>
                """
                st.markdown(button_style, unsafe_allow_html=True)
            st.button(agent_name, key=f"agent_{index}", on_click=agent_button_callback(index))


def display_agent_edit_form(agent, edit_index):
    with st.expander(f"Edit Properties of {agent['config'].get('name', '')}", expanded=True):
        new_name = st.text_input("Name", value=agent['config'].get('name', ''), key=f"name_{edit_index}")
        description_value = agent.get('new_description', agent.get('description', ''))
        new_description = st.text_area("Description", value=description_value, key=f"desc_{edit_index}")
        if st.button(" Regenerate", key=f"regenerate_{edit_index}"):
            print(f"Regenerate button clicked for agent {edit_index}")
            new_description = regenerate_agent_description(agent)
            if new_description:
                agent['new_description'] = new_description
                print(f"Description regenerated for {agent['config']['name']}: {new_description}")
                st.experimental_rerun()
            else:
                print(f"Failed to regenerate description for {agent['config']['name']}")
        if st.button("Save Changes", key=f"save_{edit_index}"):
            agent['config']['name'] = new_name
            agent['description'] = agent.get('new_description', new_description)
            st.session_state['show_edit'] = False
            if 'edit_agent_index' in st.session_state:
                del st.session_state['edit_agent_index']
            if 'new_description' in agent:
                del agent['new_description']
            # Update the agent data in the session state
            st.session_state.agents[edit_index] = agent
            st.success("Agent properties updated")        
            print("Contents of st.session_state.agents after saving the regenerated agent:")
            regenerate_json_files_and_zip()


def download_agent_file(expert_name):
    # Format the expert_name
    formatted_expert_name = re.sub(r'[^a-zA-Z0-9\s]', '', expert_name)  # Remove non-alphanumeric characters
    formatted_expert_name = formatted_expert_name.lower().replace(' ', '_')  # Convert to lowercase and replace spaces with underscores

    # Get the full path to the agent JSON file
    agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "agents"))
    json_file = os.path.join(agents_dir, f"{formatted_expert_name}.json")

    # Check if the file exists
    if os.path.exists(json_file):
        # Read the file content
        with open(json_file, "r") as f:
            file_content = f.read()

        # Encode the file content as base64
        b64_content = base64.b64encode(file_content.encode()).decode()

        # Create a download link
        href = f'<a href="data:application/json;base64,{b64_content}" download="{formatted_expert_name}.json">Download {formatted_expert_name}.json</a>'
        st.markdown(href, unsafe_allow_html=True)
    else:
        st.error(f"File not found: {json_file}")


def process_agent_interaction(agent_index):
    agent_name, description = retrieve_agent_information(agent_index)
    user_request = st.session_state.get('user_request', '')
    user_input = st.session_state.get('user_input', '')
    rephrased_request = st.session_state.get('rephrased_request', '')
    reference_url = st.session_state.get('reference_url', '')
    request = construct_request(agent_name, description, user_request, user_input, rephrased_request, reference_url)
    response = send_request(agent_name, request)
    if response:
        update_discussion_and_whiteboard(agent_name, response, user_input)
        st.session_state['form_agent_name'] = agent_name
        st.session_state['form_agent_description'] = description
        st.session_state['selected_agent_index'] = agent_index

        request = f"Act as the {agent_name} who {description}."
        if user_request:
            request += f" Original request was: {user_request}."
        if rephrased_request:
            request += f" You are helping a team work on satisfying {rephrased_request}."
        if user_input:
            request += f" Additional input: {user_input}."
        if reference_url:
            try:
                response = requests.get(reference_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                url_content = soup.get_text()
                request += f" Reference URL content: {url_content}."
            except requests.exceptions.RequestException as e:
                print(f"Error occurred while retrieving content from {reference_url}: {e}")
        if st.session_state.discussion:
            request += f" The discussion so far has been {st.session_state.discussion[-50000:]}."

        api_key = get_api_key()
        if api_key is None:
            st.error("API key not found. Please enter your API key.")
            return

        response = send_request_to_groq_api(agent_name, request, api_key)
        if response:
            update_discussion_and_whiteboard(agent_name, response, user_input)
            # Additionally, populate the sidebar form with the agent's information
            st.session_state['form_agent_name'] = agent_name
            st.session_state['form_agent_description'] = description
            st.session_state['selected_agent_index'] = agent_index # Keep track of the selected agent for potential updates/deletes


def regenerate_agent_description(agent):
    agent_name = agent['config']['name']
    print(f"agent_name: {agent_name}")
    agent_description = agent['description']
    print(f"agent_description: {agent_description}")
    user_request = st.session_state.get('user_request', '')
    print(f"user_request: {user_request}")
    discussion_history = st.session_state.get('discussion_history', '')

    prompt = f"""
    You are an AI assistant helping to improve an agent's description. The agent's current details are:
    Name: {agent_name}
    Description: {agent_description}

    The current user request is: {user_request}

    The discussion history so far is: {discussion_history}

    Please generate a revised description for this agent that defines it in the best manner possible to address the current user request, taking into account the discussion thus far. Return only the revised description, without any additional commentary or narrative.  It is imperative that you return ONLY the text of the new description.  No preamble, no narrative, no superfluous commentary whatsoever.  Just the description, unlabeled, please.
    """

    api_key = get_api_key()
    if api_key is None:
        st.error("API key not found. Please enter your API key.")
        return None

    print(f"regenerate_agent_description called with agent_name: {agent_name}")
    print(f"regenerate_agent_description called with prompt: {prompt}")

    response = send_request_to_groq_api(agent_name, prompt, api_key)
    if response:
        return response.strip()
    else:
        return None


def retrieve_agent_information(agent_index):
    agent = st.session_state.agents[agent_index]
    agent_name = agent["config"]["name"]
    description = agent["description"]
    return agent_name, description


def send_request(agent_name, request):
    api_key = get_api_key()
    if api_key is None:
        st.error("API key not found. Please enter your API key.")
        return None
    response = send_request_to_groq_api(agent_name, request, api_key)
    return response