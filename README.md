# 🤖 TDS Data Analyst Agent

A powerful AI-driven data analysis platform that combines the capabilities of Google's Generative AI with advanced data processing tools to provide intelligent insights, visualizations, and automated analysis workflows.

## 📊 Overview

The TDS Data Analyst Agent is a web-based application that transforms how you interact with data. Upload your datasets and questions, and receive comprehensive analysis with interactive visualizations, statistical insights, and AI-powered recommendations.

### Key Features

- **🔍 Intelligent Data Analysis**: AI-powered insights using Google's Generative AI
- **📈 Interactive Visualizations**: Dynamic charts and graphs using Matplotlib and Seaborn
- **🌐 Web Scraping**: Extract data from URLs and web pages
- **📁 Multi-Format Support**: CSV, Excel, JSON, Parquet, and text files
- **🔄 Batch Processing**: Analyze multiple questions simultaneously
- **🎨 Modern UI**: Beautiful, responsive web interface
- **⚡ Real-time Processing**: Fast analysis with progress tracking

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Google Generative AI API key
- Modern web browser

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Project_2
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   Create a `.env` file in the project root:
   ```env
   GOOGLE_API_KEY=your_google_generative_ai_api_key_here
   LLM_TIMEOUT_SECONDS=150
   ```

4. **Run the application**
   ```bash
   python app.py
   ```

5. **Access the application**
   Open your browser and navigate to `http://localhost:8000`

## 📖 Usage Guide

### 1. Prepare Your Questions
Create a text file (`.txt`) with your analysis questions. Each question should be on a separate line:

```
What are the key trends in the sales data?
Which products have the highest profit margins?
Show me a correlation analysis between variables A and B
```

### 2. Upload Your Data
- **Questions File**: Required - Your analysis questions in `.txt` format
- **Dataset**: Optional - Your data in CSV, Excel, JSON, Parquet, or text format

### 3. Get Results
The agent will:
- Process your questions and data
- Generate comprehensive analysis
- Create interactive visualizations
- Provide AI-powered insights and recommendations

## 🛠️ Technical Architecture

### Backend Stack
- **FastAPI**: High-performance web framework
- **LangChain**: LLM orchestration and tool integration
- **Google Generative AI**: Advanced AI capabilities
- **Pandas & NumPy**: Data manipulation and analysis
- **Matplotlib & Seaborn**: Data visualization

### Frontend
- **HTML5/CSS3**: Modern, responsive interface
- **JavaScript**: Interactive user experience
- **Bootstrap-inspired styling**: Professional appearance

### Data Processing Capabilities
- **File Formats**: CSV, Excel, JSON, Parquet, TXT
- **Web Scraping**: HTML tables, API endpoints
- **Data Cleaning**: Automatic preprocessing
- **Statistical Analysis**: Descriptive and inferential statistics

## 🔧 API Endpoints

### Core Endpoints

#### `GET /`
- **Description**: Serve the main web interface
- **Response**: HTML frontend

#### `POST /analyze`
- **Description**: Process questions and data for analysis
- **Parameters**:
  - `questions_file`: Text file with analysis questions
  - `data_file`: Optional dataset file
- **Response**: JSON with analysis results and visualizations

#### `POST /scrape`
- **Description**: Extract data from web URLs
- **Parameters**:
  - `url`: Target URL to scrape
- **Response**: JSON with extracted data

### Tool Functions

#### `scrape_url_to_dataframe(url)`
Extracts data from web pages, supporting:
- HTML tables
- CSV files
- Excel files
- JSON data
- Plain text

#### `analyze_dataframe_with_llm(data, questions)`
Performs AI-powered analysis on datasets with:
- Statistical summaries
- Trend analysis
- Correlation studies
- Anomaly detection
- Predictive insights

## 📊 Supported Data Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| CSV | `.csv` | Comma-separated values |
| Excel | `.xlsx`, `.xls` | Microsoft Excel files |
| JSON | `.json` | JavaScript Object Notation |
| Parquet | `.parquet` | Columnar storage format |
| Text | `.txt` | Plain text files |

## 🎯 Use Cases

### Business Intelligence
- Sales performance analysis
- Customer behavior insights
- Market trend identification
- Financial data analysis

### Research & Analytics
- Academic research support
- Statistical analysis
- Data exploration
- Hypothesis testing

### Data Science
- Exploratory data analysis
- Feature engineering insights
- Model performance evaluation
- Data quality assessment

## 🔒 Security & Privacy

- **Local Processing**: Data is processed locally on your server
- **No Data Storage**: Files are processed in memory and not stored
- **API Key Protection**: Secure environment variable handling
- **CORS Configuration**: Configurable cross-origin resource sharing

## 🚀 Deployment

### Local Development
```bash
python app.py
```

### Production Deployment
1. Set up a production server (AWS, GCP, Azure, etc.)
2. Install dependencies: `pip install -r requirements.txt`
3. Configure environment variables
4. Use a production WSGI server like Gunicorn:
   ```bash
   gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker
   ```

### Docker Deployment
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "app.py"]
```

## 📝 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_API_KEY` | Google Generative AI API key | Required |
| `LLM_TIMEOUT_SECONDS` | Timeout for LLM operations | 150 |

### Customization Options
- Modify visualization styles in the frontend CSS
- Adjust analysis parameters in the tool functions
- Configure CORS settings for production deployment
- Customize the LLM prompt templates

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and add tests
4. Commit your changes: `git commit -am 'Add feature'`
5. Push to the branch: `git push origin feature-name`
6. Submit a pull request

### Development Setup
```bash
# Install development dependencies
pip install -r requirements.txt

# Run tests (when available)
python -m pytest

# Format code
black app.py
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support & Troubleshooting

### Common Issues

**API Key Error**
- Ensure your Google Generative AI API key is correctly set in the `.env` file
- Verify the API key has the necessary permissions

**File Upload Issues**
- Check file format compatibility
- Ensure file size is within limits
- Verify file encoding (UTF-8 recommended)

**Analysis Timeout**
- Increase `LLM_TIMEOUT_SECONDS` in your `.env` file
- Consider breaking large datasets into smaller chunks

### Getting Help
- Check the [Issues](../../issues) page for known problems
- Create a new issue for bugs or feature requests
- Review the code documentation for technical details

## 🔮 Roadmap

### Upcoming Features
- [ ] Real-time collaboration
- [ ] Advanced statistical models
- [ ] Custom visualization templates
- [ ] API rate limiting and caching
- [ ] Multi-language support
- [ ] Mobile application

### Version History
- **v1.0.0**: Initial release with core analysis capabilities
- **v1.1.0**: Added web scraping functionality
- **v1.2.0**: Enhanced visualization options

---

**Built with ❤️ using FastAPI, LangChain, and Google Generative AI**
