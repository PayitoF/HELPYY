import React, { createContext, useContext, useState, useCallback, useMemo, useEffect } from 'react';
import useAgentState from '../hooks/useAgentState';
import useChat from '../hooks/useChat';

const AgentContext = createContext(null);

const SESSION_ID = 'app_' + Math.random().toString(36).slice(2, 10);
const LS_KEY = 'helpyy_account';

export function AgentProvider({ children }) {
  const agentState = useAgentState();
  const [userProfile, setUserProfile] = useState({ name: null, accountId: null });
  const [isBanked, setIsBanked] = useState(false);
  const [helpyyActive, setHelpyyActive] = useState(false);
  const [isFreshAccount, setIsFreshAccount] = useState(false);
  const [hasStoredAccount, setHasStoredAccount] = useState(false);

  // Profile in-flight before PIN is created
  const [pendingProfile, setPendingProfile] = useState(null);

  // Check localStorage on mount
  useEffect(() => {
    const stored = JSON.parse(localStorage.getItem(LS_KEY) || 'null');
    if (stored?.pin) setHasStoredAccount(true);
  }, []);

  const chat = useChat(SESSION_ID, {
    isBanked,
    onMetadata: (meta) => {
      if (meta.display_name || meta.account_id) {
        setUserProfile({ name: meta.display_name || null, accountId: meta.account_id || null });
      }
      if (meta.helpyy_enabled) {
        setIsBanked(true);
        setHelpyyActive(true);
        // Update stored account with helpyyActive if one exists
        const stored = JSON.parse(localStorage.getItem(LS_KEY) || 'null');
        if (stored) {
          localStorage.setItem(LS_KEY, JSON.stringify({ ...stored, helpyyActive: true }));
        }
      }
      if (meta.account_id && !meta.helpyy_enabled) {
        setIsBanked(true);
      }
    },
  });

  const [showActivationModal, setShowActivationModal] = useState(false);
  const [helpyyPanelOpen, setHelpyyPanelOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);

  const activateHelpyy = useCallback(() => {
    setHelpyyActive(true);
    setShowActivationModal(false);
    const stored = JSON.parse(localStorage.getItem(LS_KEY) || 'null');
    if (stored) {
      localStorage.setItem(LS_KEY, JSON.stringify({ ...stored, helpyyActive: true }));
    }
  }, []);

  const triggerActivation = useCallback(() => {
    setShowActivationModal(true);
  }, []);

  // Stage a profile waiting for PIN creation (does NOT set isBanked yet)
  const preparePinSetup = useCallback((profile) => {
    setPendingProfile(profile);
  }, []);

  // Called after PIN is confirmed — persists to localStorage and enters the app
  const savePinAndLogin = useCallback((pin) => {
    if (!pendingProfile) return;
    const account = {
      accountId: pendingProfile.accountId,
      displayName: pendingProfile.name,
      pin,
      cedula: pendingProfile.cedula || '',
      helpyyActive: pendingProfile.helpyyActive || false,
      isFreshAccount: true,
    };
    localStorage.setItem(LS_KEY, JSON.stringify(account));
    setUserProfile({ name: account.displayName, accountId: account.accountId });
    setHelpyyActive(account.helpyyActive);
    setIsFreshAccount(true);
    setHasStoredAccount(true);
    setPendingProfile(null);
    setIsBanked(true);
  }, [pendingProfile]);

  // Called by returning-user PIN login screen (cedula + PIN auth)
  const loginWithPin = useCallback((cedula, pin) => {
    const stored = JSON.parse(localStorage.getItem(LS_KEY) || 'null');
    if (!stored || stored.pin !== pin) return false;
    // Verify cedula only if one is stored (code-activation accounts may not have cedula)
    if (stored.cedula && stored.cedula !== String(cedula).trim()) return false;
    setUserProfile({ name: stored.displayName, accountId: stored.accountId });
    setHelpyyActive(stored.helpyyActive || false);
    setIsFreshAccount(stored.isFreshAccount !== false);
    setIsBanked(true);
    return true;
  }, []);

  // Log out current session without clearing stored account
  const logout = useCallback(() => {
    setIsBanked(false);
    setUserProfile({ name: null, accountId: null });
    setHelpyyActive(false);
    setIsFreshAccount(false);
    setPendingProfile(null);
  }, []);

  // Clear stored account (used by "No eres tú" / logout)
  const clearStoredAccount = useCallback(() => {
    localStorage.removeItem(LS_KEY);
    setHasStoredAccount(false);
    setPendingProfile(null);
  }, []);

  // Legacy alias — kept so old call sites don't break during transition
  const activateFromCode = useCallback((profile) => {
    preparePinSetup({ ...profile, helpyyActive: true });
  }, [preparePinSetup]);

  const value = useMemo(() => ({
    ...agentState,
    ...chat,
    helpyyActive,
    showActivationModal,
    helpyyPanelOpen,
    notifications,
    unreadCount,
    userProfile,
    isBanked,
    isFreshAccount,
    hasStoredAccount,
    pendingProfile,
    setIsBanked,
    activateFromCode,
    preparePinSetup,
    savePinAndLogin,
    loginWithPin,
    logout,
    clearStoredAccount,
    activateHelpyy,
    triggerActivation,
    setHelpyyPanelOpen,
    setShowActivationModal,
    setNotifications,
    setUnreadCount,
    sessionId: SESSION_ID,
  }), [
    agentState, chat, helpyyActive, showActivationModal,
    helpyyPanelOpen, notifications, unreadCount,
    userProfile, isBanked, isFreshAccount, hasStoredAccount, pendingProfile,
    activateFromCode, preparePinSetup, savePinAndLogin, loginWithPin, logout,
    clearStoredAccount, activateHelpyy, triggerActivation,
  ]);

  return (
    <AgentContext.Provider value={value}>
      {children}
    </AgentContext.Provider>
  );
}

export function useAgent() {
  const context = useContext(AgentContext);
  if (!context) throw new Error('useAgent must be used within AgentProvider');
  return context;
}
