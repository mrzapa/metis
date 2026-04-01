(() => {
  try {
    let stored = window.localStorage.getItem("metis-ui-variant");
    if (!stored) {
      const legacy = window.localStorage.getItem("metis-ui-variant");
      if (legacy) {
        window.localStorage.setItem("metis-ui-variant", legacy);
        window.localStorage.removeItem("metis-ui-variant");
        stored = legacy;
      }
    }
    const variant = stored === "refined" || stored === "motion" || stored === "bold" ? stored : "refined";
    document.documentElement.dataset.uiVariant = variant;
  } catch {
    document.documentElement.dataset.uiVariant = "refined";
  }
})();
