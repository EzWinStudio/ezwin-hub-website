# EZWIN HUB Web Sitesi

EZWIN HUB'ın tarayıcı sürümü. Statik HTML/CSS/JS; harici çalışma zamanı bağımlılığı yoktur.

- Canlı: https://ezwin-hub.wasmer.app
- Yayın: Wasmer Edge (`ezwinstudio/ezwin-hub`)
- Kaynak: `public/` klasörü
- Sınırlama: Tarayıcı sürümü canlı Discord/Pterodactyl/Gmail kontrolü yapmaz; sahte durum göstermez. Canlı bot ve site izleme için Windows masaüstü uygulamasını kullanın.
- Tüm kaynak: https://github.com/EzWinStudio/ezwin-hub-app

## Yayınlama

```sh
wasmer deploy --non-interactive --owner ezwinstudio --app-name ezwin-hub --dir . --publish-package
```

## İndir

[ZIP olarak indir](https://github.com/EzWinStudio/ezwin-hub-website/archive/refs/heads/main.zip)
