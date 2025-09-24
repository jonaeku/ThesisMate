import chainlit as cl
import asyncio
from typing import AsyncGenerator
from src.orchestrator.orchestrator import Orchestrator
from src.utils.logging import get_logger

logger = get_logger(__name__)

@cl.on_chat_start
async def on_chat_start():
    """Initialize the chat session with an orchestrator instance"""
    cl.user_session.set("orchestrator", Orchestrator())
    
    # Send welcome message
    welcome_msg = """
    Welcome to ThesisMate! 🎓
    
    I'm your AI-powered thesis writing assistant. I can help you with:
    - Finding and evaluating thesis topics
    - Researching academic papers and sources  
    - Creating thesis structure and outlines
    - Writing assistance and content generation
    - Reviewing and providing feedback
    
    What would you like to work on today?
    """
    await cl.Message(content=welcome_msg).send()

@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming messages with streaming support and timeout handling"""
    orchestrator = cl.user_session.get("orchestrator")
    
    if not orchestrator:
        await cl.Message(content="Session error. Please refresh the page.").send()
        return
    
    # Create a message to show processing status
    processing_msg = cl.Message(content="🔄 Processing your request...")
    await processing_msg.send()
    
    try:
        # Run orchestrator with timeout and streaming
        result = await run_with_streaming(orchestrator, message.content, processing_msg)
        
        # Update the processing message with final result
        processing_msg.content = result
        await processing_msg.update()
        
    except asyncio.TimeoutError:
        error_msg = """
        ⏰ **Request Timeout**
        
        Your request is taking longer than expected. This might be due to:
        - Complex research queries requiring extensive paper searches
        - Multiple agent collaborations
        - External API delays
        
        Please try:
        - Breaking down complex requests into smaller parts
        - Being more specific about what you need
        - Trying again in a moment
        """
        processing_msg.content = error_msg
        await processing_msg.update()
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        error_msg = f"""
        ❌ **Processing Error**
        
        An error occurred while processing your request: {str(e)}
        
        Please try rephrasing your request or contact support if the issue persists.
        """
        processing_msg.content = error_msg
        await processing_msg.update()

async def run_with_streaming(orchestrator: Orchestrator, query: str, status_msg: cl.Message, timeout: int = 300) -> str:
    """
    Run orchestrator with streaming updates and timeout handling
    
    Args:
        orchestrator: The orchestrator instance
        query: User query
        status_msg: Message to update with progress
        timeout: Timeout in seconds (default 5 minutes)
    """
    
    async def update_status_periodically():
        """Update status message periodically to show progress"""
        status_messages = [
            "🔄 Processing your request...",
            "🤖 Routing to appropriate agent...",
            "🔍 Analyzing your query...",
            "📚 Searching for relevant information...",
            "⚙️ Generating response...",
            "🔄 Almost done..."
        ]
        
        for i, status in enumerate(status_messages):
            await asyncio.sleep(10)  # Update every 10 seconds
            if status_msg:
                status_msg.content = status
                try:
                    await status_msg.update()
                except:
                    pass  # Ignore update errors
    
    async def run_orchestrator():
        """Run the orchestrator in a separate task"""
        # Run orchestrator in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, orchestrator.run, query)
    
    # Start both tasks
    status_task = asyncio.create_task(update_status_periodically())
    orchestrator_task = asyncio.create_task(run_orchestrator())
    
    try:
        # Wait for orchestrator with timeout
        result = await asyncio.wait_for(orchestrator_task, timeout=timeout)
        
        # Cancel status updates
        status_task.cancel()
        
        return result
        
    except asyncio.TimeoutError:
        # Cancel both tasks
        status_task.cancel()
        orchestrator_task.cancel()
        raise
    
    except Exception as e:
        # Cancel status task and re-raise
        status_task.cancel()
        raise

@cl.on_stop
async def on_stop():
    """Clean up when chat stops"""
    logger.info("Chat session ended")

# Configure Chainlit settings for better timeout handling
@cl.on_settings_update
async def setup_agent(settings):
    """Handle settings updates"""
    pass
