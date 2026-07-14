import React, { useState, useEffect } from "react";
import DashboardDesktop from "./DashboardDesktop";
import DashboardMobile from "./DashboardMobile";

export default function Dashboard(props) {
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (isMobile) {
    return <DashboardMobile {...props} />;
  }
  
  return <DashboardDesktop {...props} />;
}
