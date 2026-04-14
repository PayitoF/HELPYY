import { useState, useCallback, useRef } from 'react';

const TRANSITION_MS = 400;

export default function useAgentState() {
  const [activeAgent, setActiveAgentRaw] = useState(null);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [agentHistory, setAgentHistory] = useState([]);
  const timeoutRef = useRef(null);

  const setActiveAgent = useCallback((agent) => {
    setIsTransitioning(true);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      setActiveAgentRaw((prev) => {
        if (prev && prev !== agent) {
          setAgentHistory((h) => [...h, prev]);
        }
        return agent;
      });
      setIsTransitioning(false);
    }, TRANSITION_MS);
  }, []);

  return { activeAgent, isTransitioning, setActiveAgent, agentHistory };
}
