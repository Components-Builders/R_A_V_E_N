import React from 'react';
import { StatSegment } from 'src/useRaven';

const SEP = '  •  ';
const STATSNAMES = [
    'Current model',
    'Context usage',
    'Token usage',
    'Memory usage',
]

// {i > 0 && <span className="stats-sep">{SEP}</span>}

type Props = { segments: StatSegment[] };

// const StatsBlock = ({ segments }: Props) => {
//     if (!segments.length) {
//         return <div className="stats-block">R.A.V.E.N</div>;
//     }
//     return (
//         <div className="flex flex-col gap-5 font-header">
//             {segments.map((seg, i) => (
//                 <div key={seg.name} className=' p-2.5 border-2 border-ink hover:bg-ink flex flex-col items-start hover:text-white select-none transition-colors duration-200'>
//                     <span className='text-[0.75em] font-sora text-ink-dim'>
//                         {STATSNAMES[i]}
//                     </span>
//                     {seg.text}
//                     {i == 3 &&
//                         <div className='w-full h-4 relative bg-ink-dim/30'>
//                             <span style={{
//                                 width: `${Number(seg.text.match(/\d+/)?.[0])}%`
//                             }}
//                              className='h-full absolute top-0 left-0 bg-ink'></span>
//                         </div>}
//                 </div>
//             ))}
//         </div>
//     );
// };

const StatsBlock = ({ segments }: Props) => {
    if (!segments.length) {
        return <div className="stats-block text-ink ">R.A.V.E.N -- Waiting for stats</div>;
    }
    return (
        <div className="flex flex-col gap-2 font-header">
            {segments.map((seg, i) => (
                <div key={seg.name} className='group p-2.5 border-ink hover:bg-strong flex flex-col items-start hover:text-onstrong select-none transition-colors duration-200'>
                    <span className='text-[0.75em] font-sora text-ink-dim group-hover:text-onstrong/65'>
                        {STATSNAMES[i]}
                    </span>
                    {seg.text}
                    {i == 3 &&
                        <div className='w-full h-4 relative bg-ink-dim/30 group-hover:bg-onstrong/35'>
                            <span style={{
                                width: `${Number(seg.text.match(/\d+/)?.[0])}%`
                            }}
                             className='h-full absolute top-0 left-0 bg-ink group-hover:bg-onstrong'></span>
                        </div>}
                </div>
            ))}
        </div>
    );
};

export default StatsBlock;