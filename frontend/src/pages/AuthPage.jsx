import React, { useState, useEffect } from 'react';
import { login, sendOtp, verifyOtp, registerFinalize, getMe } from '../api';
import { useAuth } from '../AuthContext';
import './AuthPage.css';

export default function AuthPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [step, setStep] = useState(1); // 1: Info, 2: OTP, 3: Password & Keys
  const [formData, setFormData] = useState({
    username: '', email: '', name: '', phone: '',
    otp: '',
    password: '', confirmPassword: '',
    deviceName: 'Web Browser'
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [animateCard, setAnimateCard] = useState(false);
  const { loginUser } = useAuth();

  useEffect(() => {
    setAnimateCard(true);
    const timer = setTimeout(() => setAnimateCard(false), 600);
    return () => clearTimeout(timer);
  }, [isLogin]);

  const handleSwitch = (e) => {
    e.preventDefault();
    setAnimateCard(true);
    setTimeout(() => {
      setIsLogin(!isLogin);
      setStep(1);
      setError('');
      setFormData(prev => ({ ...prev, otp: '', password: '', confirmPassword: '' }));
    }, 150);
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const urlEncoded = new URLSearchParams();
      urlEncoded.append('username', formData.username);
      urlEncoded.append('password', formData.password);
      const { access_token } = await login(urlEncoded);
      localStorage.setItem('token', access_token);
      const user = await getMe();
      loginUser(access_token, user);
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleSignupStep1 = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await sendOtp({ email: formData.email });
      setStep(2);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to send OTP');
    } finally {
      setLoading(false);
    }
  };

  const handleSignupStep2 = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await verifyOtp({ email: formData.email, otp: formData.otp });
      setStep(3);
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid OTP');
    } finally {
      setLoading(false);
    }
  };

  const handleSignupStep3 = async (e) => {
    e.preventDefault();
    if (formData.password !== formData.confirmPassword) {
      return setError('Passwords do not match');
    }

    setError('');
    setLoading(true);
    try {
      await registerFinalize({
        name: formData.name,
        phone: formData.phone,
        email: formData.email,
        otp: formData.otp,
        username: formData.username,
        password: formData.password,
        confirm_password: formData.confirmPassword,
        device_name: formData.deviceName
      });

      // Automatically login
      const urlEncoded = new URLSearchParams();
      urlEncoded.append('username', formData.username);
      urlEncoded.append('password', formData.password);
      const { access_token } = await login(urlEncoded);
      localStorage.setItem('token', access_token);
      const user = await getMe();
      loginUser(access_token, user);
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const stepLabels = ['Details', 'Verify', 'Password'];

  return (
    <div className="auth-page">
      {/* Animated gradient background */}
      <div className="auth-bg">
        <div className="auth-bg-gradient"></div>
        <div className="auth-bg-orb auth-bg-orb--1"></div>
        <div className="auth-bg-orb auth-bg-orb--2"></div>
        <div className="auth-bg-orb auth-bg-orb--3"></div>
        <div className="auth-bg-orb auth-bg-orb--4"></div>
        <div className="auth-bg-mesh"></div>
      </div>

      {/* Glass card */}
      <div className={`auth-glass-card ${animateCard ? 'auth-glass-card--animate' : ''}`}>
        {/* Logo / Brand */}
        <div className="auth-brand">
          <div className="auth-brand-icon">
            <svg viewBox="0 0 24 24" fill="none" width="28" height="28">
              <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <h1 className="auth-brand-title">Crime Nexus</h1>
          <p className="auth-brand-subtitle">
            {isLogin ? 'Welcome back, Officer' : 'Join the Intelligence Network'}
          </p>
        </div>

        {/* Page title */}
        <h2 className="auth-title">{isLogin ? 'Login' : 'Create Account'}</h2>

        {/* Step indicator for signup */}
        {!isLogin && (
          <div className="auth-steps">
            {stepLabels.map((label, idx) => (
              <div key={idx} className={`auth-step ${step > idx + 1 ? 'auth-step--done' : ''} ${step === idx + 1 ? 'auth-step--active' : ''}`}>
                <div className="auth-step-dot">
                  {step > idx + 1 ? (
                    <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
                      <path d="M13.485 3.515a1 1 0 0 1 0 1.414l-6.364 6.364a1 1 0 0 1-1.414 0L2.515 8.1a1 1 0 1 1 1.414-1.414l2.121 2.121 5.657-5.657a1 1 0 0 1 1.414 0z"/>
                    </svg>
                  ) : (
                    <span>{idx + 1}</span>
                  )}
                </div>
                <span className="auth-step-label">{label}</span>
                {idx < stepLabels.length - 1 && <div className="auth-step-line"></div>}
              </div>
            ))}
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="auth-error">
            <svg viewBox="0 0 20 20" width="16" height="16" fill="currentColor">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd"/>
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* ─── Login Form ───────────────────────────────────────────── */}
        {isLogin ? (
          <form onSubmit={handleLogin} className="auth-form">
            <div className="auth-field">
              <input
                id="login-username"
                type="text"
                className="auth-input"
                placeholder=" "
                value={formData.username}
                onChange={e => setFormData({...formData, username: e.target.value})}
                required
                autoComplete="username"
              />
              <label htmlFor="login-username" className="auth-label">Username</label>
              <div className="auth-input-line"></div>
            </div>

            <div className="auth-field">
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                className="auth-input"
                placeholder=" "
                value={formData.password}
                onChange={e => setFormData({...formData, password: e.target.value})}
                required
                autoComplete="current-password"
              />
              <label htmlFor="login-password" className="auth-label">Password</label>
              <div className="auth-input-line"></div>
              <button
                type="button"
                className="auth-eye-toggle"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? (
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </button>
            </div>

            <div className="auth-options">
              <label className="auth-checkbox-label" htmlFor="remember-me">
                <input type="checkbox" id="remember-me" className="auth-checkbox" />
                <span className="auth-checkbox-custom"></span>
                Remember Me
              </label>
              <a href="#" className="auth-forgot-link" onClick={e => e.preventDefault()}>
                Forgot Password?
              </a>
            </div>

            <button type="submit" className="auth-submit-btn" disabled={loading}>
              {loading ? (
                <span className="auth-spinner"></span>
              ) : (
                <>
                  Log in
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M5 12h14M12 5l7 7-7 7"/>
                  </svg>
                </>
              )}
            </button>
          </form>
        ) : (
          <>
            {/* ─── Signup Step 1: Basic Info ────────────────────────── */}
            {step === 1 && (
              <form onSubmit={handleSignupStep1} className="auth-form" key="step1">
                <div className="auth-field">
                  <input
                    id="signup-username"
                    type="text"
                    className="auth-input"
                    placeholder=" "
                    value={formData.username}
                    onChange={e => setFormData({...formData, username: e.target.value})}
                    required
                  />
                  <label htmlFor="signup-username" className="auth-label">Username</label>
                  <div className="auth-input-line"></div>
                </div>

                <div className="auth-field">
                  <input
                    id="signup-email"
                    type="email"
                    className="auth-input"
                    placeholder=" "
                    value={formData.email}
                    onChange={e => setFormData({...formData, email: e.target.value})}
                    required
                  />
                  <label htmlFor="signup-email" className="auth-label">Email Address</label>
                  <div className="auth-input-line"></div>
                </div>

                <div className="auth-field">
                  <input
                    id="signup-name"
                    type="text"
                    className="auth-input"
                    placeholder=" "
                    value={formData.name}
                    onChange={e => setFormData({...formData, name: e.target.value})}
                    required
                  />
                  <label htmlFor="signup-name" className="auth-label">Full Name</label>
                  <div className="auth-input-line"></div>
                </div>

                <div className="auth-field">
                  <input
                    id="signup-phone"
                    type="text"
                    className="auth-input"
                    placeholder=" "
                    value={formData.phone}
                    onChange={e => setFormData({...formData, phone: e.target.value})}
                    required
                  />
                  <label htmlFor="signup-phone" className="auth-label">Phone Number</label>
                  <div className="auth-input-line"></div>
                </div>

                <button type="submit" className="auth-submit-btn" disabled={loading}>
                  {loading ? (
                    <span className="auth-spinner"></span>
                  ) : (
                    <>
                      Send OTP
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M5 12h14M12 5l7 7-7 7"/>
                      </svg>
                    </>
                  )}
                </button>
              </form>
            )}

            {/* ─── Signup Step 2: OTP Verification ──────────────────── */}
            {step === 2 && (
              <form onSubmit={handleSignupStep2} className="auth-form" key="step2">
                <p className="auth-otp-info">
                  We've sent a verification code to<br/>
                  <strong>{formData.email}</strong>
                </p>

                <div className="auth-field">
                  <input
                    id="signup-otp"
                    type="text"
                    className="auth-input auth-input--otp"
                    placeholder=" "
                    value={formData.otp}
                    onChange={e => setFormData({...formData, otp: e.target.value})}
                    required
                    maxLength={6}
                    autoComplete="one-time-code"
                  />
                  <label htmlFor="signup-otp" className="auth-label">Enter OTP Code</label>
                  <div className="auth-input-line"></div>
                </div>

                <button type="submit" className="auth-submit-btn" disabled={loading}>
                  {loading ? (
                    <span className="auth-spinner"></span>
                  ) : (
                    <>
                      Verify Code
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="20 6 9 17 4 12"/>
                      </svg>
                    </>
                  )}
                </button>

                <button
                  type="button"
                  className="auth-back-btn"
                  onClick={() => setStep(1)}
                >
                  ← Back to Details
                </button>
              </form>
            )}

            {/* ─── Signup Step 3: Set Password ──────────────────────── */}
            {step === 3 && (
              <form onSubmit={handleSignupStep3} className="auth-form" key="step3">
                <div className="auth-field">
                  <input
                    id="signup-password"
                    type={showPassword ? 'text' : 'password'}
                    className="auth-input"
                    placeholder=" "
                    value={formData.password}
                    onChange={e => setFormData({...formData, password: e.target.value})}
                    required
                  />
                  <label htmlFor="signup-password" className="auth-label">Password</label>
                  <div className="auth-input-line"></div>
                  <button
                    type="button"
                    className="auth-eye-toggle"
                    onClick={() => setShowPassword(!showPassword)}
                    tabIndex={-1}
                  >
                    {showPassword ? (
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/>
                        <line x1="1" y1="1" x2="23" y2="23"/>
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                    )}
                  </button>
                </div>

                <div className="auth-field">
                  <input
                    id="signup-confirm-password"
                    type={showConfirmPassword ? 'text' : 'password'}
                    className="auth-input"
                    placeholder=" "
                    value={formData.confirmPassword}
                    onChange={e => setFormData({...formData, confirmPassword: e.target.value})}
                    required
                  />
                  <label htmlFor="signup-confirm-password" className="auth-label">Confirm Password</label>
                  <div className="auth-input-line"></div>
                  <button
                    type="button"
                    className="auth-eye-toggle"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    tabIndex={-1}
                  >
                    {showConfirmPassword ? (
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/>
                        <line x1="1" y1="1" x2="23" y2="23"/>
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                    )}
                  </button>
                </div>

                <button type="submit" className="auth-submit-btn" disabled={loading}>
                  {loading ? (
                    <span className="auth-spinner"></span>
                  ) : (
                    <>
                      Create Account
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M5 12h14M12 5l7 7-7 7"/>
                      </svg>
                    </>
                  )}
                </button>

                <button
                  type="button"
                  className="auth-back-btn"
                  onClick={() => setStep(2)}
                >
                  ← Back
                </button>
              </form>
            )}
          </>
        )}

        {/* Toggle login/signup */}
        <div className="auth-toggle">
          <span>
            {isLogin ? "Don't have an account?" : 'Already have an account?'}
          </span>
          <a href="#" onClick={handleSwitch} className="auth-toggle-link">
            {isLogin ? 'Register' : 'Log in'}
          </a>
        </div>
      </div>
    </div>
  );
}
