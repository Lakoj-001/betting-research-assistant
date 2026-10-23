# Script 1: send "hello" to Claude and print the reply.

from dotenv import load_dotenv
import anthropic

# Read the keys from .env into this program's environment.
load_dotenv()

# The client finds ANTHROPIC_API_KEY by itself once load_dotenv() has run.
client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-haiku-5-5",  # the cheapest model, for testing
    max_tokens=200,            # caps how long the reply can be
    messages=[{"role": "user", "content": "Hello! Say hi back in one sentence."}],
)

# The reply arrives as a list of blocks. The first one holds the text.
print(response.content[0].text)
