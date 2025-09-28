import { VideoStudio } from '@/components/video-studio'

export const metadata = {
  title: 'Studio vidéo | SEIDRA',
  description: 'Montez vos vidéos avec timeline, piste audio et prévisualisation image par image.',
}

export default function VideoStudioPage() {
  return (
    <main className="mx-auto max-w-6xl space-y-12 px-6 pb-16 pt-12">
      <section className="rounded-3xl border border-purple-500/40 bg-black/40 p-6 text-purple-100 shadow-xl">
        <h1 className="text-2xl font-semibold text-yellow-200">Bienvenue dans le studio vidéo</h1>
        <p className="mt-2 text-sm text-purple-200">
          Ce module est pensé comme un espace d’assemblage rapide : importez vos assets, agencez-les sur la timeline puis
          déclenchez un rendu proxy pour valider le montage avant d’envoyer la composition finale vers le pipeline haute
          résolution.
        </p>
        <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm text-purple-100">
          <li>
            <strong className="text-yellow-200">Importez des vidéos, audios ou images</strong> – Le panneau « Assets » accepte le
            glisser-déposer et génère automatiquement des waveforms audio consultables dans la piste dédiée.
          </li>
          <li>
            <strong className="text-yellow-200">Disposez vos clips sur la timeline</strong> – Les pistes sont accessibles au clavier
            et prennent en charge la navigation par flèches ainsi que la suppression directe.
          </li>
          <li>
            <strong className="text-yellow-200">Générez un rendu proxy</strong> – Un preview basse résolution est calculé pour un
            retour quasi instantané avant d’envoyer un rendu définitif.
          </li>
        </ol>
        <p className="mt-4 text-xs text-purple-300">
          Astuce : en l’absence d’assets, une page de documentation détaillant les formats recommandés et les raccourcis est
          disponible dans <em>doc/studio-video-onboarding.md</em>.
        </p>
      </section>
      <VideoStudio />
    </main>
  )
}
