import Image from 'next/image';

type Props = { small?: boolean };

export default function KpuLogo({ small = false }: Props) {
  return (
    <Image
      src="/logo-kpu.png"
      alt="Logo KPU"
      width={small ? 28 : 36}
      height={small ? 31 : 40}
      className={small ? 'kpu-logo kpu-logo-small' : 'kpu-logo'}
      priority={!small}
    />
  );
}
