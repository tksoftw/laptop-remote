'use strict';
importScripts('/vendor/zxing-reader.js');
ZXingWASM.prepareZXingModule({overrides: {
  locateFile(path) {
    if (path !== 'zxing_reader.wasm') throw new Error('Unexpected QR reader resource.');
    return '/vendor/zxing_reader.wasm';
  },
}});

self.onmessage = async ({data}) => {
  try {
    const codes = await ZXingWASM.readBarcodes(data, {
      formats: ['QRCode'], tryHarder: true, tryRotate: true,
      tryInvert: true, tryDownscale: true, tryDenoise: true,
      maxNumberOfSymbols: 2, textMode: 'Plain',
    });
    if (!codes.length) throw new Error('No readable QR code found. Move closer and keep the entire code in focus and free of glare.');
    if (codes.length !== 1) throw new Error('More than one QR code found. Take a photo of only the Laptop Remote code.');
    self.postMessage({text: codes[0].text});
  } catch (error) {
    self.postMessage({error: error.message || 'The QR reader failed.'});
  }
};
