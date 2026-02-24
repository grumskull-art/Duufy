(() => {
  const bannerId = "offline-banner";
  const bannerText = "Du er offline \u2013 \u00e6ndringer gemmes lokalt";

  const showBanner = () => {
    if (!document.body || document.getElementById(bannerId)) {
      return;
    }
    const banner = document.createElement("div");
    banner.id = bannerId;
    banner.textContent = bannerText;
    document.body.prepend(banner);
  };

  const hideBanner = () => {
    const banner = document.getElementById(bannerId);
    if (banner) {
      banner.remove();
    }
  };

  window.addEventListener("offline", showBanner);
  window.addEventListener("online", hideBanner);

  if (!navigator.onLine) {
    showBanner();
  }
})();
