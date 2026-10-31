// On-demand Apple Vision OCR. No network and no persistent receipt storage.
import Foundation
import Vision
import ImageIO
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.revision = VNRecognizeTextRequestRevision3
request.usesCPUOnly = true
request.usesLanguageCorrection = false
let handler = VNImageRequestHandler(url: url)
do {
    try handler.perform([request])
    for line in request.results ?? [] {
        if let candidate = line.topCandidates(1).first { print(candidate.string) }
    }
} catch {
    let failure = error as NSError
    fputs("OCR error: \(failure.domain) \(failure.code)\n", stderr)
    exit(1)
}
