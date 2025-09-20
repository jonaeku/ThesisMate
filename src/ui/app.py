import chainlit as cl
from src.orchestrator.orchestrator import Orchestrator

@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("orchestrator", Orchestrator())

@cl.on_message
async def on_message(message: cl.Message):
    orchestrator = cl.user_session.get("orchestrator")
    result = orchestrator.run(message.content)
    await cl.Message(content=result).send()
