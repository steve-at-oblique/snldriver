; =================================================================
; QL Serial Block String Test (SER2H)
; =================================================================

START
            movem.l d1-d7/a0-a6,-(a7)
            ; 1. Open channel "SER2H"
            lea     SERNAME(pc),a0
            moveq   #-1,d1              ; Owning job: current job
            moveq   #0,d2               ; Open existing serial device
            moveq   #1,d0               ; IO.OPEN ($01)
            trap    #2                  
            tst.l   d0                  
            bne.s   EXIT                
            
            move.l  a0,d7               ; Save Channel ID pointer in D7

            ; 2. Prepare message pointer and loop counter
            lea     MSG(pc),a1
            move.w  (a1)+,d6            ; Get string length into D6

SENDLOOP
            move.b  (a1)+,d1            ; Get next byte into D1

            move.l  d7,a0               ; TRAP #3 takes channel ID in A0
            moveq   #-1,d3              ; Wait for serial output
            moveq   #5,d0               ; Operation code $05 (iob.sbyt)
            trap    #3                  ; Send single byte
            tst.l   d0
            bne.s   SENDFAIL

            subq.w  #1,d6               ; Decrement character counter
            bne.s   SENDLOOP            ; Repeat until all bytes sent

            ; 3. Close the channel
            move.l  d7,a0               
            moveq   #2,d0               ; IO.CLOSE ($02)
            trap    #2                  

EXIT
            movem.l (a7)+,d1-d7/a0-a6
            rts                         

SENDFAIL
            move.l  d0,d6               ; Preserve send error while closing
            move.l  d7,a0
            moveq   #2,d0
            trap    #2
            move.l  d6,d0
            bra.s   EXIT

SERNAME
            dc.w    5                   
            dc.b    'SER2H'
            dc.b    0                   ; Pad the five-byte name to an even length

MSG
            dc.w    15                  ; 14 printable characters plus LF
            dc.b    'Hello from QL!',10  

            END
