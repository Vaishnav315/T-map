import React, { useState, useEffect } from "react";
import AIAnalyticsDesktop from "./AIAnalyticsDesktop";
import AIAnalyticsMobile from "./AIAnalyticsMobile";

export default function AIAnalytics(props) {
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (isMobile) {
    return <AIAnalyticsMobile {...props} />;
  }
  
  return <AIAnalyticsDesktop {...props} />;
}
