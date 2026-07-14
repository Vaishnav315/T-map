import React, { useState, useEffect } from "react";
import HistoryDesktop from "./HistoryDesktop";
import HistoryMobile from "./HistoryMobile";

export default function History(props) {
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (isMobile) {
    return <HistoryMobile {...props} />;
  }
  
  return <HistoryDesktop {...props} />;
}
