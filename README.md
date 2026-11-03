# Orbita Web

Orbita'nın tarayıcı ve telefon (PWA) sürümü. React/TypeScript uygulamasının statik üretim çıktısıdır.

- Canlı: https://orbita.wasmer.app
- Windows indirme sayfası: https://orbita.wasmer.app/indir/
- Eski adres (aynı sürüm): https://ezwin-hub.wasmer.app
- Yayın: Wasmer Edge (`ezwinstudio/orbita`)
- Kaynak: `public/` klasörü
- Telefon: Android/Chrome ve iPhone/Safari menüsünden **Ana ekrana ekle** ile PWA olarak kurulur.
- Eşitleme: Ayarlar > Cihaz eşitleme. Veriler AES-GCM ile şifrelenir; sunucu yalnızca şifreli paketi saklar. Bot tokenları ve şifreler eşitlenmez.
- Sınırlama: Tarayıcı sürümü sahte canlı durum üretmez; site ve bot kontrolleri masaüstü uygulamasında yapılır.
- Tüm kaynak: https://github.com/EzWinStudio/ezwin-hub-app

## Yayınlama

```sh
wasmer deploy --non-interactive --publish-package
```

Bu depo derlenmiş `public/` çıktısını içerir. Kaynak değişikliğinde ana depoda `npm run build:web` çalıştırıp `web-dist/` içeriğini `public/` ile değiştirin.

## İndir

[ZIP olarak indir](https://github.com/EzWinStudio/ezwin-hub-website/archive/refs/heads/main.zip)
