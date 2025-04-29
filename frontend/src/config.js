const isDevelopment = process.env.NODE_ENV === 'development';

// In development, we'll use localhost
// In production, we'll use the deployed backend URL
const API_URL = isDevelopment 
  ? 'http://localhost:8001'
  : process.env.REACT_APP_API_URL || 'https://hindisetu-api.onrender.com';

export { API_URL }; 