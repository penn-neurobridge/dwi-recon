function [vec, vec_neg] = charToCartesian(charVec)
    % Convert character representations of 3D unit vectors to Cartesian coordinates

    switch charVec
        case 'i'
            vec = [1, 0, 0];
            vec_neg = [-1 , 0, 0];
        case 'j'
            vec = [0, 1, 0];
            vec_neg = [0, -1, 0];
        case 'k'
            vec = [0, 0, 1];
            vec_neg = [0, 0, -1];
        case {'-i', 'i-'}
            vec = [-1, 0, 0];
            vec_neg = [1, 0, 0];
        case {'-j', 'j-'}
            vec = [0, -1, 0];
            vec_neg = [0, 1, 0];
        case {'-k', 'k-'} 
            vec = [0, 0, -1];
            vec_neg = [0, 0, 1];
        otherwise
            error('Invalid input character.');
    end
end