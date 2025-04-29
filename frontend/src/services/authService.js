import api from './axiosConfig';

const validateAuthResponse = (data) => {
  if (!data.access || !data.refresh || !data.user) {
    throw new Error('Invalid response from server: missing authentication data');
  }
  if (data.access === 'undefined' || data.refresh === 'undefined') {
    throw new Error('Invalid authentication tokens received from server');
  }
  return data;
};

const authService = {
  login: async (email, password) => {
    try {
      const response = await api.post('/auth/login/', {
        email,
        password,
      });
      
      const validatedData = validateAuthResponse(response.data);
      localStorage.setItem('accessToken', validatedData.access);
      localStorage.setItem('refreshToken', validatedData.refresh);
      localStorage.setItem('userInfo', JSON.stringify(validatedData.user));
      
      return validatedData;
    } catch (error) {
      if (error.response?.status === 401) {
        throw { message: 'Invalid email or password' };
      }
      throw error.response?.data || { message: 'An error occurred during login' };
    }
  },

  signup: async (userData) => {
    try {
      const response = await api.post('/auth/signup/', userData);
      
      const validatedData = validateAuthResponse(response.data);
      localStorage.setItem('accessToken', validatedData.access);
      localStorage.setItem('refreshToken', validatedData.refresh);
      localStorage.setItem('userInfo', JSON.stringify(validatedData.user));
      
      return validatedData;
    } catch (error) {
      if (error.response?.status === 400) {
        throw { message: 'Email already exists or invalid data provided' };
      }
      throw error.response?.data || { message: 'An error occurred during signup' };
    }
  },

  logout: async () => {
    try {
      const refreshToken = localStorage.getItem('refreshToken');
      if (refreshToken && refreshToken !== 'undefined') {
        await api.post('/auth/logout/', { refresh: refreshToken });
      }
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      localStorage.removeItem('accessToken');
      localStorage.removeItem('refreshToken');
      localStorage.removeItem('userInfo');
      window.location.href = '/login';
    }
  },

  getCurrentUser: () => {
    const userInfo = localStorage.getItem('userInfo');
    if (!userInfo || userInfo === 'undefined') {
      return null;
    }
    try {
      return JSON.parse(userInfo);
    } catch {
      localStorage.removeItem('userInfo');
      return null;
    }
  },

  isAuthenticated: () => {
    const accessToken = localStorage.getItem('accessToken');
    const refreshToken = localStorage.getItem('refreshToken');
    return (
      !!accessToken && 
      !!refreshToken && 
      accessToken !== 'undefined' && 
      refreshToken !== 'undefined'
    );
  }
};

export default authService; 