# Orbita Web

Orbita 2.6.5 tarayıcı, telefon (PWA), masaüstü ve Android sürümü. React/TypeScript uygulamasının statik üretim çıktısı ve Wasmer Edge sunucusu.

- Sürüm: 2.6.5 (masaüstü ve Android otomatik güncelleme, pano kopyalama düzeltmesi)
- Canlı: https://orbita.wasmer.app
- İndirme sayfası: https://orbita.wasmer.app/indir/
- Kaynak: https://github.com/EzWinStudio/Orbita
- Sürümler: https://github.com/EzWinStudio/Orbita/releases
- Yayın: Wasmer Edge (`ezwinstudio/orbita`), Python/Flask sunucu ve `public/` statik çıktısı
- Masaüstü: Windows kurulum ve taşınabilir paket; uygulama yeni sürümü GitHub'dan otomatik denetler, SHA-256 ile doğrular ve kapatırken kurar.
- Android: APK; uygulama içinden güncelleme denetimi, indirme ve doğrulama yapılır. İlk kurulumda Android'in bilinmeyen kaynak izni ve sistem kurulum onayı gerekir.
- Hesaplar: Wasmer MySQL üzerinde sunucu oturumu; şifreler scrypt ile doğrulanır. Eşitleme paketleri AES-GCM ile şifrelenir; sunucu yalnızca şifreli paketi saklar.
- Telefon: Android/Chrome ve iPhone/Safari menüsünden **Ana ekrana ekle** ile PWA olarak kurulur.
- Sınırlama: Tarayıcı sürümü sahte canlı durum üretmez; site ve bot kontrolleri masaüstü uygulamasında yapılır.

## Yayınlama

```sh
wasmer deploy --non-interactive --dir .
```

Bu depo derlenmiş `public/` çıktısını ve `server/` kaynağını içerir. Kaynak değişikliğinde ana depoda `npm run build:web` çalıştırıp `web-dist/` içeriğini `public/` ile değiştirin; sunucu değişikliklerini `server/` altına kopyalayın.

Kurulum dosyaları GitHub Releases üzerinde tutulur; bu depoda yalnızca SHA-256 dosyaları bulunur. `/download/Orbita-Setup-*.exe` istekleri GitHub sürümüne yönlendirilir.

## İndir

[ZIP olarak indir](https://github.com/EzWinStudio/ezwin-hub-website/archive/refs/heads/main.zip)
