export default function Logo({ className = "", size = "sm" }: { className?: string; size?: "sm" | "md" | "lg" }) {
  const heights = {
    sm: 'clamp(4rem, 8vw + 2rem, 6rem)',
    md: 'clamp(7rem, 16vw + 2rem, 10rem)',
    lg: 'clamp(10rem, 30vw + 4rem, 28rem)',
  };

  return (
    <img 
      src="/assets/logo.png" 
      alt="zubchek" 
      className={className}
      style={{ 
        height: heights[size],
        width: 'auto',
        maxWidth: '90vw'
      }}
    />
  );
}