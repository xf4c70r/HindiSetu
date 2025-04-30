const config = {
    API_URL: process.env.REACT_APP_API_URL 
        ? `${process.env.REACT_APP_API_URL}/api`
        : process.env.NODE_ENV === 'production'
            ? 'https://hindisetubackend.onrender.com/api'
            : 'http://localhost:8001/api'
};

// Log configuration for debugging
console.log('Environment:', process.env.NODE_ENV);
console.log('API URL:', config.API_URL);
console.log('Raw REACT_APP_API_URL:', process.env.REACT_APP_API_URL);

export default config; 