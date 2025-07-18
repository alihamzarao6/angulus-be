# Angulus Backend

A FastAPI-based backend application that provides AI agent capabilities with web scraping and data processing features.

## System Architecture

The application is built using:
- FastAPI for the web framework
- MongoDB for data storage
- OpenAI API for AI capabilities
- Various tools for web scraping and data processing

## Prerequisites

- Python 3.8 or higher
- MongoDB instance
- OpenAI API key
- Docker (optional, for containerized deployment)

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd angulus-be
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Unix/MacOS:
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
Create a `.env` file in the root directory with:
```
OPENAI_API_KEY=your_openai_api_key
MONGO_URI=your_mongodb_connection_string
DB_NAME=your_mongodb_name
BASE_URL=base_url_for_the_application
```

## Running the Application

### Development Mode
```bash
python app.py
```
The server will start at `http://localhost:5000`

### Docker Deployment
```bash
docker build -t angulus-be .
docker run -p 5000:5000 angulus-be
```

## Key Components

### API Endpoints

1. **Base Endpoint**
   - `GET /`: Welcome message and API status

2. **Message Handling**
   - `POST /message`: Send messages to the AI agent
   - `POST /agents/message`: Run specific agent tasks

3. **Agent Management**
   - `GET /agents`: List all available agents
   - `POST /agents`: Create a new agent
   - `GET /agents/{agent_id}`: View agent details

4. **Tools and Utilities**
   - `GET /tools`: List available tools
   - `GET /prompt-history`: Get conversation history

### Core Features

1. **AI Agents**
   - Customizable agents with specific instructions
   - Support for multiple tools and capabilities
   - Language translation capabilities

2. **Web Scraping**
   - Single page scraping
   - Multiple page scraping with ZIP output
   - Table data extraction to CSV

3. **Data Processing**
   - JSON parsing utilities
   - MongoDB integration
   - Static file serving

## Project Structure

```
angulus-be/
├── app.py              # Main application file
├── db.py              # Database configuration
├── tools.py           # Tool implementations
├── utils.py           # Utility functions
├── seed.py            # Database seeding
├── json_parser.py     # JSON parsing utilities
├── requirements.txt   # Project dependencies
├── Dockerfile         # Docker configuration
└── output/           # Static file output directory
```

## Development

### Adding New Tools
1. Implement the tool in `tools.py`
2. Register the tool in the database using `seed.py`
3. Update agent configurations to use the new tool

### Creating Custom Agents
1. Use the `/agents` POST endpoint
2. Specify agent name, instructions, and required tools
3. The agent will be available for use immediately

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Specify your license here] 