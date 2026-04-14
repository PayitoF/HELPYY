import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AgentProvider, useAgent } from './contexts/AgentContext';
import BankDashboard from './components/BankDashboard';
import PreLoginScreen from './components/PreLoginScreen';

function AppContent() {
  const { isBanked } = useAgent();

  return (
    <AnimatePresence mode="wait">
      {isBanked ? (
        <motion.div
          key="dashboard"
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 1.04 }}
          transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] }}
        >
          <BankDashboard />
        </motion.div>
      ) : (
        <motion.div
          key="prelogin"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0, y: -30 }}
          transition={{ duration: 0.4 }}
        >
          <PreLoginScreen />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <AgentProvider>
      <AppContent />
    </AgentProvider>
  );
}
