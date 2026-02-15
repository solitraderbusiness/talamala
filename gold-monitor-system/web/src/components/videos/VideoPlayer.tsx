"use client";

interface VideoPlayerProps {
  youtubeId: string;
  title?: string;
}

export default function VideoPlayer({ youtubeId, title }: VideoPlayerProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 dark:border-gray-700">
      <div className="aspect-video">
        <iframe
          src={`https://www.youtube.com/embed/${youtubeId}?rel=0`}
          className="h-full w-full"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          title={title || "Video"}
        />
      </div>
    </div>
  );
}
