import React, { createContext, useContext, useState, useEffect } from 'react';
import { getMe, logoutUserApi } from './api';

const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('token');
      if (token) {
        try {
          const userData = await getMe();
          setUser(userData);
        } catch (err) {
          localStorage.removeItem('token');
        }
      }
      setLoading(false);
    };
    initAuth();
  }, []);

  const loginUser = (token, userData) => {
    localStorage.setItem('token', token);
    setUser(userData);
  };

  const logoutUser = async () => {
    try {
      await logoutUserApi();
    } catch (e) {
      console.error('Logout API failed', e);
    }
    localStorage.removeItem('token');
    setUser(null);
  };

  const updateUser = (userData) => {
    setUser(userData);
  };

  return (
    <AuthContext.Provider value={{ user, loginUser, logoutUser, updateUser, loading }}>
      {children}
    </AuthContext.Provider>
  );
};
